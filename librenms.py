import urllib3, requests, re, os
from ansible.module_utils.six.moves.urllib.parse import urljoin
from ansible.errors import AnsibleError
from ansible.plugins.inventory import BaseInventoryPlugin, Constructable, Cacheable
from unidecode import unidecode


DOCUMENTATION = '''
    name: librenms
    plugin_type: inventory
    author:
        - Mikhail Shchedrin mschedrin@gmail.com 
    short_description:
        - LibreNMS inventory source
    description:
        - Get inventory hosts from LibreNMS
    extends_documentation_fragment:
        - inventory_cache
    options:
        plugin:
            description: token that ensures this is a source file for the 'librenms' plugin.
            required: True
            choices: ['librenms']
        api_endpoint:
            description: Endpoint of the LibreNMS API
            required: True
            env:
                - name: LIBRENMS_API
        validate_certs:
            description:
                - Allows connection when SSL certificates are not valid. Set to C(false) when certificates are not trusted.
            default: True
            type: boolean
        api_token:
            required: True
            description: Librenms token.
            env:
                # in order of precedence
                - name: LIBRENMS_TOKEN
                - name: LIBRENMS_API_KEY
        exclude_disabled:
            type: bool
            default: True
        cache_force_update:
            description: Force inventory cache update regardless cache timeouts
            type: bool
            default: False
        cache_connection:
            default: /tmp
        cache_plugin: 
            default: pickle
        regex_ignore_case:
            type: bool
            default: True
        group_by:
            description: Create ansible groups from libre device properties
            type: str
            default: ''
        group_name_regex_filter:
            description: Regex filters for group names
            type: list
            default: []
        host_name_regex_filter:
            description: Regex filters for host names
            type: list
            default: []
        timeout:
            description: Timeout for LibreNMS requests in seconds
            type: int
            default: 60
        verbose:
            decription: Enable verbose output
            type: bool
            default: False
'''


class InventoryModule(BaseInventoryPlugin, Constructable, Cacheable):
    NAME = 'librenms'  # used internally by Ansible, it should match the file name but not required
    re_flags = 0
    libre_to_ansible_variable_mapping = { #map certain variable names to ansible names
        'hostname': 'ansible_host',
        'libre_hostname': 'ansible_host',
        'os': 'ansible_network_os',
        'libre_os': 'ansible_network_os'
    }
    libre_to_ansible_os_mapping = {
        'asa': 'asa',
        'ios':'ios',
        'iosxe':'ios'}
    def _log(self, *args):
        if self.verbose:
            print(args[0])

    def _http_request(self, url):
        r = requests.get(url, headers=self.headers, verify=self.validate_certs)
        if r.json()['status'] == "error":
            #libre returns error if there is zero devices in the group. WTF? Here is workaround:
            if "No devices found in group" in r.json()['message']:
                return dict()
            else:
                raise AnsibleError(r.json()['message'])
        return r.json()

    def _filter_device_groups(self, device_groups, filters):
        result = list()
        for f in filters:
            result += [ grp for grp in device_groups['groups'] if \
                       re.match(f, grp['name'], self.re_flags)  ]
        return result

    def _filter_device_hostnames(self, devices, filters):
        result = list()
        for f in filters:
            result += [ dev for dev in devices if re.match(f, dev['sysName'], self.re_flags) ]
        return result

    def _check_device_match_filters(self, device, filters):
        for f in filters:
            if re.match(f, device['sysName'], self.re_flags):
                return device
        return False

    def _get_devices_from_group(self, device_group):
        url = self.api_endpoint+'/devicegroups/'+device_group['name']
        response = self._http_request(url)
        return response.get('devices', list())

    def _get_device_by_id(self, device_id):
        url = self.api_endpoint+'/devices/'+str(device_id)
        device = self._http_request(url)
        return device['devices'][0]

    def _set_host_variables(self, hostname, variables_list):
        for variable_name, value in variables_list.items():
            variable_name = self.libre_to_ansible_variable_mapping.get(variable_name, variable_name)
            self.inventory.set_variable(hostname, variable_name, value)
            if variable_name == 'ansible_network_os':
                value = self.libre_to_ansible_os_mapping.get(value, value)
                self.inventory.set_variable(hostname, variable_name, value)

    def _add_device(self, device, group_name):
        if device['libre_sysName'] is None:
            hostname = device['libre_hostname']
        elif len(device['libre_sysName']):
            hostname = unidecode(device['libre_sysName'])
        else:
            hostname = device['libre_hostname']
        #self._log(device)
        self._log(f"Adding host: {hostname}")
        if not (device['libre_disabled'] > 0 and self.exclude_disabled) or \
            (device['libre_disabled'] == 0):
            self.inventory.add_host(group=group_name, host=hostname)
            self._set_host_variables(hostname, device)

    def _add_group(self, group_name):
        #self.inventory.add_group(unidecode(group_name))
        self.inventory.add_group(group_name)

    def _build_source_data(self):
        source_data={
            'host_name_regex_filter': self.host_name_regex_filter,
            'group_name_regex_filter': self.group_name_regex_filter,
            'inventory': {} }
        #get device groups
        url = self.api_endpoint+'/devicegroups'
        all_device_groups = self._http_request(url)
        if self.group_name_regex_filter:
            device_groups = self._filter_device_groups(all_device_groups, \
                                                       self.group_name_regex_filter)
        else: 
            device_groups = all_device_groups['groups']

        #get devices from groups
        for grp in device_groups:
            self._log("Processing group: "+grp['name'])
            device_ids_dict = self._get_devices_from_group(grp)
            for device_id_dict in device_ids_dict:
                if self.host_name_regex_filter:
                    tmp_dev = self._check_device_match_filters(\
                        self._get_device_by_id(device_id_dict['device_id']), \
                            self.host_name_regex_filter)
                else:
                    tmp_dev = self._get_device_by_id(device_id_dict['device_id'])
                if tmp_dev:
                    #prefix keys with 'libre_'
                    prefixed_tmp_dev = dict( ('libre_'+key, val) for key,val in tmp_dev.items() )
                    #save filter parameters on each host variable
                    prefixed_tmp_dev['inventory_group_name_regex_filter'] = (self.group_name_regex_filter)
                    prefixed_tmp_dev['inventory_host_name_regex_filter'] = (self.host_name_regex_filter)
                    if self.group_by:
                        # Set empty list for group if it doesn't exist
                        source_data['inventory'].setdefault(tmp_dev[self.group_by], list())
                        source_data['inventory'][tmp_dev[self.group_by]].append(prefixed_tmp_dev)
                    else:
                        source_data['inventory'].setdefault(grp['name'], list())
                        source_data['inventory'][grp['name']].append(prefixed_tmp_dev)
        return source_data

    def _populate_ansible_inventory(self, source_data):
        inventory = source_data['inventory']
        for group_name, hosts in inventory.items():
            print("Processing group: "+group_name)
            self._add_group(group_name) # add group to ansible
            for host in hosts:
                self._add_device(host, group_name)

    def parse(self, inventory, loader, path, cache=True):
        # call base method to ensure properties are available for use with other helper methods
        super(InventoryModule, self).parse(inventory, loader, path, cache=cache)
        self.config = self._read_config_data(path=path)
        self.api_endpoint = self.get_option("api_endpoint")
        self.api_token = self.get_option("api_token") if self.get_option("api_token") \
            else os.getenv('LIBRENMS_TOKEN')
        self.validate_certs = self.get_option("validate_certs")
        self.group_by = self.get_option("group_by")
        self.group_name_regex_filter = self.get_option("group_name_regex_filter")
        self.host_name_regex_filter = self.get_option("host_name_regex_filter")
        self.exclude_disabled = self.get_option("exclude_disabled")
        self.cache_force_update = self.get_option("cache_force_update")
        if self.get_option("regex_ignore_case"):
            self.re_flags = re.IGNORECASE

        if not self.validate_certs:
            urllib3.disable_warnings()
        self.timeout = self.get_option("timeout")
        self.verbose = self.get_option("verbose")
        self.headers = { 'X-Auth-Token': self.api_token }
        self._log("Plugin configuration:")
        self._log(self.config)
        #self._log(self.group_name_regex_filter)
        #self._log(self.host_name_regex_filter)

        cache_key = self.get_cache_key(path)
        self._log(f"Cache location: {self.get_option('cache_connection')}{cache_key}")
        self._log("Plugin path: "+path)

        if cache: #if caching enabled globally
            cache = self.get_option('cache') #read cache parameter from plugin config
        source_data = None
        update_cache = True
        if cache and not self.cache_force_update: # if cache is enabled and is not forced to be updated
            try:
                source_data = self._cache.get(cache_key)
                update_cache = False
                self._log("Got data from cache")
                #self._log(source_data)
            except KeyError:
                self._log("Fail reading cache")
                update_cache = True

        #Check that filter saved in cache is the same as current. If they don't match rebuild cache!
        if source_data and cache and not update_cache:
            if self.group_name_regex_filter != source_data['group_name_regex_filter'] or \
               self.host_name_regex_filter != source_data['host_name_regex_filter']:
                self._log("Current inventory filters do not match cached data, force cache update")
                update_cache = True

        if not source_data or update_cache:
            self._log("Don't use cache, get fresh meat from Libre")
            source_data = self._build_source_data()

        if cache:
            self._cache[cache_key] = source_data
            self._log("Cache saved to selected storage plugin")

        self._log("Populate ansible inventory")
        self._populate_ansible_inventory(source_data)

# TODO: fix documentation part to work with ansible: ansible-doc -t inventory librenms
# TODO: evaluate composited vars: self._set_composite_vars function, see example in netbox inventory plugin
#https://github.com/ansible/ansible/blob/devel/lib/ansible/plugins/inventory/netbox.py
