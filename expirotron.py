from datetime import datetime, timedelta
from deluge_client import DelugeRPCClient
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from tabulate import tabulate
import smtplib
import ssl
import os
import sys


def reformat(torrents):
    parsed = []
    for i in torrents:
        parsed.append({i: torrents[i]})
    return parsed


def filter_accepted_age(torrent):
    accepted_age = datetime.now() - timedelta(days=14)
    torrent_id = list(torrent.keys())[0]
    time_added = datetime.fromtimestamp(torrent[torrent_id][b"time_added"])
    name = torrent[torrent_id][b"name"]
    if accepted_age > time_added:
        return True
    else:
        print(f"Filtering {name} because its age is not below the threshold")
        return False


def filter_accepted_labels(torrent):
    accepted = [b"tv-sonarr", b"radarr"]
    torrent_id = list(torrent.keys())[0]
    label = torrent[torrent_id][b"label"]
    name = torrent[torrent_id][b"name"]
    if label in accepted:
        return True
    else:
        print(f"Filtering {name} because its label is not accepted")
        return False


def filter_accepted_tracker_status(torrent):
    accepted = [b"Announce OK", b""]
    torrent_id = list(torrent.keys())[0]
    tracker_status = torrent[torrent_id][b"tracker_status"]
    name = torrent[torrent_id][b"name"]
    if tracker_status not in accepted:
        return True
    else:
        print(f"Filtering {name} because its tracker status is accepted")
        return False


def filter_ratio(torrent):
    torrent_id = list(torrent.keys())[0]
    ratio = torrent[torrent_id][b"ratio"]
    progress = torrent[torrent_id][b"progress"]
    name = torrent[torrent_id][b"name"]
    if progress == 100 and ratio >= 1:
        return True
    else:
        print(f"Filtering {name} because its ratio is not >= 1")
        return False


def filter_seeders(torrent):
    torrent_id = list(torrent.keys())[0]
    name = torrent[torrent_id][b"name"]
    total_seeds = torrent[torrent_id][b"total_seeds"]
    time_since_download = torrent[torrent_id][b"time_since_download"]
    time_since_download_days = timedelta(seconds=time_since_download).days
    if total_seeds == 0 and time_since_download_days > 7:
        return True
    else:
        print(f"Filtering {name} because its ratio it has seeds")
        return False


def torrent_ids(torrent):
    return list(torrent.keys())[0]


env_vars = [
    "DELUGE_IP",
    "DELUGE_PASSWORD",
    "DELUGE_PORT",
    "DELUGE_USER",
    "SMTP_HOST",
    "SMTP_PASSWORD",
    "SMTP_PORT",
    "SMTP_USER",
]

for env_var in env_vars:
    if os.environ.get(env_var) is None:
        print(f"{env_var} must be defined in the environment")
        sys.exit(1)


keys = [
    "is_finished",
    "is_seed",
    "label",
    "name",
    "progress",
    "ratio",
    "state",
    "time_added",
    "time_since_download",
    "time_since_transfer",
    "time_since_upload",
    "total_peers",
    "total_seeds",
    "tracker_status",
]

client = DelugeRPCClient(
    os.environ.get("DELUGE_IP"),
    int(os.environ.get("DELUGE_PORT")),
    os.environ.get("DELUGE_USER"),
    os.environ.get("DELUGE_PASSWORD"),
)
client.connect()

torrents = client.call("core.get_torrents_status", {}, keys)

reformated_torrents = reformat(torrents)

accepted_label = list(filter(filter_accepted_labels, reformated_torrents))

remove = []

# tracker = list(filter(filter_accepted_tracker_status, accepted_label))
# tracker_ids = list(map(torrent_ids, tracker))
# for id in tracker_ids:
# torrents[id].setdefault("reason", []).append("tracker")
# remove.append(id)

age = list(filter(filter_accepted_age, accepted_label))
age_ids = list(map(torrent_ids, age))
for id in age_ids:
    torrents[id].setdefault("reason", []).append("age")
    remove.append(id)

ratio = list(filter(filter_ratio, accepted_label))
ratio_ids = list(map(torrent_ids, ratio))
for id in ratio_ids:
    torrents[id].setdefault("reason", []).append("ratio")
    remove.append(id)

seeders = list(filter(filter_seeders, accepted_label))
seeders_ids = list(map(torrent_ids, seeders))
for id in seeders_ids:
    torrents[id].setdefault("reason", []).append("seeders")
    remove.append(id)

names = []
for id in remove:
    # import ipdb; ipdb.set_trace()
    name_long = torrents[id][b"name"].decode("utf-8")
    name = (name_long[:40] + '...') if len(name_long) > 40 else name_long
    total_seeds = torrents[id][b"total_seeds"]
    progress = round(torrents[id][b"progress"])
    ratio = round(torrents[id][b"ratio"], 2)
    reason = " ".join(torrents[id]["reason"])
    time_added = torrents[id][b'time_added']
    time_since_download = torrents[id][b'time_since_download']
    age = (datetime.now() - datetime.fromtimestamp(time_added)).days
    tracker_status = torrents[id][b'tracker_status']
    state = torrents[id][b'state']
    names.append(
        {
            "Name": name,
            "Reason": reason,
            'State': state,
            "Progress": progress,
            "Ratio": ratio,
            'Seeders': total_seeds,
            'Age': age,
            'Since D/L': timedelta(seconds=time_since_download).days,
            'Status': tracker_status
        }
    )
    print(f"Removing {name_long}...")
    client.call('core.remove_torrent', id, True)

names.sort(key=lambda x: x["Name"])

msg = MIMEMultipart('alternative')
msg["Subject"] = "Expirotron Report"
msg["From"] = "brandon@milosh.dev"
msg["To"] = "brandon@milosh.dev"

text = "The following torrents have been expired:\n\n" + \
        tabulate(names, headers="keys")

html = """\
<html>
    <head></head>
    <body>
        <p>The following torrents have been expired:</p>
        {}
    </body>
</html>
""".format(tabulate(names, headers="keys", tablefmt="html"))

part1 = MIMEText(text, 'plain')
part2 = MIMEText(html, 'html')

msg.attach(part1)
msg.attach(part2)

context = ssl.create_default_context()

smtp_host = os.environ.get("SMTP_HOST")
smtp_port = os.environ.get("SMTP_PORT")

with smtplib.SMTP(smtp_host, smtp_port) as server:
    server.ehlo()
    server.starttls()
    server.login(os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD"))
    server.ehlo()
    server.send_message(msg)
    server.quit()

# import ipdb; ipdb.set_trace()
# pp.pprint(client.call('daemon.get_method_list'))
