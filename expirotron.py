from datetime import datetime, timedelta
from deluge_client import DelugeRPCClient
from email.message import EmailMessage
from tabulate import tabulate
import smtplib
import ssl
import os
import sys

def reformat(torrents):
    parsed = []
    for i in torrents:
        parsed.append({ i: torrents[i] })
    return parsed

def filter_accepted_age(torrent):
    accepted_age = datetime.now() - timedelta(days=90)
    torrent_id = list(torrent.keys())[0]
    time_added = datetime.fromtimestamp(torrent[torrent_id][b'time_added'])
    name = torrent[torrent_id][b'name']
    if accepted_age > time_added:
        return True
    else:
        print(f"Filtering {name} because its age is not below the threshold")
        return False

def filter_accepted_labels(torrent):
    accepted = [b'tv-sonarr', b'radarr']
    torrent_id = list(torrent.keys())[0]
    label = torrent[torrent_id][b'label']
    name = torrent[torrent_id][b'name']
    if label in accepted:
        return True
    else:
        print(f"Filtering {name} because its label is not accepted")
        return False

def filter_accepted_tracker_status(torrent):
    accepted = [b'Announce OK', b'']
    torrent_id = list(torrent.keys())[0]
    tracker_status = torrent[torrent_id][b'tracker_status']
    name = torrent[torrent_id][b'name']
    if tracker_status not in accepted:
        return True
    else:
        print(f"Filtering {name} because its tracker status is accepted")
        return False

def filter_ratio(torrent):
    torrent_id = list(torrent.keys())[0]
    ratio = torrent[torrent_id][b'ratio']
    progress = torrent[torrent_id][b'progress']
    if progress == 100 and ratio >= 1:
        return True
    else:
        return False
        print(f'Filtering {name} because its ratio is not >= 1')

def torrent_ids(torrent):
    return list(torrent.keys())[0]

env_vars = [ 'DELUGE_IP', 'DELUGE_PASSWORD', 'DELUGE_PORT', 'DELUGE_USER',
        'SMTP_HOST', 'SMTP_PASSWORD', 'SMTP_PORT', 'SMTP_USER' ]

for env_var in env_vars:
    if os.environ.get(env_var) == None:
        print(f'{env_var} must be defined in the environment')
        sys.exit(1)


keys = ['time_added', 'time_since_download', 'time_since_transfer',
        'time_since_upload', 'total_peers', 'total_seeds', 'is_finished',
        'is_seed', 'ratio', 'name', 'tracker_status', 'label', 'progress']

client = DelugeRPCClient(os.environ.get('DELUGE_IP'),
                        int(os.environ.get('DELUGE_PORT')),
                        os.environ.get('DELUGE_USER'),
                        os.environ.get('DELUGE_PASSWORD'))
client.connect()

torrents = client.call('core.get_torrents_status', {}, keys)

reformated_torrents = reformat(torrents)

# Filter
accepted_label = list(filter(filter_accepted_labels, reformated_torrents))
tracker = list(filter(filter_accepted_tracker_status, accepted_label))
age = list(filter(filter_accepted_age, accepted_label))
ratio = list(filter(filter_ratio, accepted_label))

# Get IDs
tracker_ids = list(map(torrent_ids, tracker))
age_ids = list(map(torrent_ids, age))
ratio_ids = list(map(torrent_ids, ratio))

remove = []
for id in tracker_ids:
    torrents[id].setdefault('reason', []).append('tracker')
    remove.append(id)

for id in age_ids:
    torrents[id].setdefault('reason', []).append('age')
    remove.append(id)

for id in ratio_ids:
    torrents[id].setdefault('reason', []).append('ratio')
    remove.append(id)

names = []
for id in remove:
    name = torrents[id][b'name']
    progress = round(torrents[id][b'progress'])
    ratio = round(torrents[id][b'ratio'], 2)
    reason = ' '.join(torrents[id]['reason'])
    # names.append(f'(progress: {progress}% ratio: {ratio}) {name.decode("utf-8")}')
    names.append({'Name': name.decode("utf-8"), 'Reason': reason, 'Progress': progress, 'Ratio': ratio})
    print(f"Removing {name}...")
    #torrents = client.call('core.remove_torrent', id, True)

names.sort(key=lambda x: x['Name'])

msg = EmailMessage()
msg['Subject'] = 'Expirotron Report'
msg['From'] = 'brandon@milosh.dev'
msg['To'] = 'brandon@milosh.dev'
msg.set_content('The following torrents have been expired due to age or torrent tracker error:\n\n' + tabulate(names, headers="keys"))

context = ssl.create_default_context()

with smtplib.SMTP(os.environ.get('SMTP_HOST'), os.environ.get('SMTP_PORT')) as server:
    server.ehlo()
    server.starttls()
    server.login(os.environ.get('SMTP_USER'), os.environ.get('SMTP_PASSWORD'))
    server.ehlo()
    server.send_message(msg)
    server.quit()

# import ipdb; ipdb.set_trace()
# pp.pprint(client.call('daemon.get_method_list'))
