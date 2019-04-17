# Description 
Ansible inventory plugin for getting ansible hosts from LibreNMS API. All LibreNMS variables are available with prefix 'libre_' in ansible inventory.
# Configuration
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