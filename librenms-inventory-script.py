#!/bin/env python

# Created by Mikhail Shchedrin mschedrin@gmail.com
'''
Before using in awx you need to install python libraries in awx conatiners:
docker exec -it awx_task bash 
cd /var/lib/awx/venv/awx/
source bin/activate
pip install configargparse unidecode
'''


import requests, re, configargparse, os, urllib3, json
from pprint import pprint
from unidecode import unidecode

#variables
exclude_disabled = True
regex_ignore_case = True
re_flags = re.IGNORECASE
validate_certs = False

libre_to_ansible_variable_mapping = { #map certain variable names to ansible names
    'hostname': 'ansible_host',
    'os': 'ansible_network_os' 
} 
libre_to_ansible_os_mapping = {
    'asa': 'asa',
    'ios':'ios',
    'iosxe':'ios' }

output = { 
    '_meta': {
        'hostvars': {
        }
    },
    'all': {
        'hosts': [],
        'vars': {}
    }
}

#functions
def _http_request(url):
    r = requests.get(url, headers=headers, verify=validate_certs)
    if r.json()['status'] == "error": 
        #libre returns error if there is zero devices in the group. WTF? Here is workaround:
        if "No devices found in group" in r.json()['message']:
            return dict()
        else:
            raise AnsibleError(r.json()['message'])
    return r.json()

def _filter_device_groups(device_groups, filters):
    result = list()
    for f in filters:
        result += [ grp for grp in device_groups['groups'] if re.match(f, grp['name'], re_flags)  ]
    return result

def _get_devices_from_group(device_group):
    url = args.libre_api_url+'/devicegroups/'+device_group['name']
    response = _http_request(url)
    return response.get('devices', list())

def _gen_groups_for_ansible(groups, aGroups=None, parentGroup=None):
    if aGroups is None: aGroups = dict()
    for g in groups:
        aGroups.setdefault(g['name'], { 'children': [], 'hosts': [] })
        if parentGroup:
            aGroups[parentGroup]['children'].append(g['name'])
        if 'childContainerIdList' in g:
            genGroupsForAnsible(g['childContainerIdList'], aGroups, g['name'])
    return aGroups

def _get_device_by_id(device_id):
    url = args.libre_api_url+'/devices/'+str(device_id)
    device = _http_request(url)
    return device['devices'][0]

def _add_group(group_name, output):
    output.update({group_name: { 'children': [], 'hosts': [] } })

def _add_device(device, group_name, output):
    if len(device['sysName']):
        hostname = unidecode(device['sysName'])
    else:
        hostname = device['hostname']
    hostVars = {}
    if not (device['disabled'] > 0 and exclude_disabled) or (device['disabled'] == 0):
        for property_name, value in device.items(): #modify host variables according to the map
            new_property_name = 'libre_'+property_name
            new_property_name = libre_to_ansible_variable_mapping.get(property_name, new_property_name)
            if new_property_name == 'ansible_network_os':
                value = libre_to_ansible_os_mapping.get(value, value)
            hostVars.update({new_property_name: value})

    output['_meta']['hostvars'][hostname] = hostVars
    output['all']['hosts'].append(hostname)
    output.setdefault( group_name, { 'hosts': list() } ) #create device group if it does not exist
    output[group_name]['hosts'].append( hostname ) #add current device to the group

#process cli args and env variables
parser = configargparse.ArgParser()
parser.add_argument("--libre-api-url", env_var='LIBRENMS_API_URL', help="api endpoint of LibreNMS", required=True)
parser.add_argument("--libre-api-token", env_var='LIBRENMS_TOKEN', help="auth token for LibreNMS", required=True)
parser.add_argument("--group-names-regex", env_var='LIBRE_GROUP_NAMES_REGEX', help="LibreNMS device group names regex filter. --group-names \"group1\" \"group2\" ", required=True, nargs='+')
parser.add_argument("--include-ip", help="include IP in yml output", action="store_true")
parser.add_argument("--list", help="list hosts", action="store_true")
args = parser.parse_args()
devGroup = args.group_names_regex
headers = { 'X-Auth-Token': args.libre_api_token }


if not validate_certs:
    urllib3.disable_warnings()
#get device groups
url = args.libre_api_url+'/devicegroups'
all_device_groups = _http_request(url)
device_groups = _filter_device_groups(all_device_groups, args.group_names_regex)

#get devices from groups
devices = list()
for grp in device_groups:
    _add_group(grp['name'], output)
    device_ids_dict = _get_devices_from_group(grp)
    for device_id_dict in device_ids_dict:
        tmp_dev = _get_device_by_id(device_id_dict['device_id'])
        _add_device(tmp_dev, grp['name'], output)

jout = json.dumps(output, indent=4, sort_keys=True)
print(jout) 