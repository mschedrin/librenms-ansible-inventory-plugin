# Description 
Ansible inventory plugin and script for getting ansible hosts from LibreNMS API. All LibreNMS variables are available with prefix 'libre_' in ansible inventory. Usage of plugin is advised as it supports caching and scripts are probably being deprecated.
# Plugin Installation and Configuration
Install dependencies `pip install unidecode`. 
Clone repository to a directory.
Find out what ansible.cfg file your installation uses by launching `ansible --version`. 

Edit ansible.cfg:
```
[defaults]
inventory_plugins = inventories # directory where librenms.py is located
[inventory]
enable_plugins = librenms
```
Create inventory plugin configuration, take libre_inventory.yml.dist as example. 

Export LibreNMS API access token as env variable: `export LIBRENMS_TOKEN=abc`

Test that inventory works: `ansible-inventory -v --list -i libre_inventory.yml`

Use for your playbooks: `ansible-playbook -i libre_inventory.yml my-playbook.yml`

# Script Installation and Configuration 
Install dependencies `pip install unidecode`. 
Clone repository to a directory.
Make script executable `chmod +x librenms-inventory-script.py`. Define environment variables `LIBRENMS_API_URL`, `LIBRENMS_TOKEN`, `LIBRE_GROUP_NAMES_REGEX`. 

Test: `ansible-inventory -v --list -i librenms-inventory-script.py`

Use for your playbooks: `ansible-playbook -i librenms-inventory-script.py my-plabook.yml`