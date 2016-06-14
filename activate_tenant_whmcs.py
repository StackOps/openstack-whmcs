# coding=utf-8

"""
   Copyright 2011-2016 STACKOPS TECHNOLOGIES S.L.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

# Find accounts with negative balance and no credit allowed and send a warning email
#
# python activate_tenant_whmcs.py ADMIN_PASSWORD
#
#

import sys
import logging
import logging.config
import ConfigParser
import hashlib
import re
import string
import random

from openstacklibs.whmcs import WHMCS
from openstacklibs.keystone import Keystone
from openstacklibs.portal import Portal
from openstacklibs.database import Portal as PortalDb
from openstacklibs.mailing import Email
from openstacklibs.mailing import TemplateText
from openstacklibs.nova import Nova
from openstacklibs.cinder import Cinder
from openstacklibs.manila import Manila
from openstacklibs.neutron import Neutron

from collections import OrderedDict

numargs = len(sys.argv)
if numargs > 3:
    initfile = str(sys.argv[3])
else:
    initfile = "./whmcs.ini"

logging.config.fileConfig(initfile)
logger_ = logging.getLogger(__name__)

config = ConfigParser.ConfigParser()
config.read(initfile)

usr = config.get('keystone', 'username')
admin_tenant_name = config.get('keystone', 'tenant')
keystone_url = config.get('keystone', 'url')
default_user_roles = config.get('keystone', 'roles').split(",")

chargeback_url = config.get('chargeback', 'url')
compute_url = config.get('compute', 'url')
volume_url = config.get('volume', 'url')
network_url = config.get('network', 'url')
manila_url = config.get('manila', 'url')
portal_url = config.get('portal', 'url')

whmcs_usr = config.get('whmcs', 'username').strip()
whmcs_password = config.get('whmcs', 'password').strip()
whmcs_url = config.get('whmcs', 'url')
whmcs_language = config.get('whmcs', 'language').strip()

database_server = config.get('portal_database', 'server')
database_username = config.get('portal_database', 'username')
database_password = config.get('portal_database', 'password')
database_schema = config.get('portal_database', 'schema')

mail_server = config.get('email', 'server')
mail_username = config.get('email', 'username')
mail_password = config.get('email', 'password')
mail_bcc = config.get('email', 'bcc')
mail_from = config.get('email', 'from')

template_portal_url = config.get('templates', 'portal_url')
template_folder = config.get('templates', 'folder')
template_subject_es = config.get('templates', 'created_subject_es')
template_subject_en = config.get('templates', 'created_subject_en')
template_file_es = config.get('templates', 'created_file_es')
template_file_en = config.get('templates', 'created_file_en')

regexp = config.get('chargeback', 'regexp')

path = config.get('app', 'path')

INSTANCES_QUOTA = config.get('quotas', 'INSTANCES_QUOTA')
CORES_QUOTA = config.get('quotas', 'CORES_QUOTA')
RAM_QUOTA = config.get('quotas', 'RAM_QUOTA')
VOLUMES_QUOTA = config.get('quotas', 'VOLUMES_QUOTA')
VOL_GB_QUOTA = config.get('quotas', 'VOL_GB_QUOTA')
SNAPSHOT_QUOTA = config.get('quotas', 'SNAPSHOT_QUOTA')
FLOATING_IPS_QUOTA = config.get('quotas', 'FLOATING_IPS_QUOTA')
METADATA_ITEMS_QUOTA = config.get('quotas', 'METADATA_ITEMS_QUOTA')
INJECTED_FILES_QUOTA = config.get('quotas', 'INJECTED_FILES_QUOTA')
INJECTED_FILE_CONTENT_BYTE_QUOTA = config.get('quotas', 'INJECTED_FILE_CONTENT_BYTE_QUOTA')
INJECTED_FILE_PATH_BYTES_QUOTA = config.get('quotas', 'INJECTED_FILE_PATH_BYTES_QUOTA')
KEY_PAIRS_QUOTA = config.get('quotas', 'KEY_PAIRS_QUOTA')
SECURITY_GROUPS_QUOTA = config.get('quotas', 'SECURITY_GROUPS_QUOTA')
SECURITY_GROUP_RULES_QUOTA = config.get('quotas', 'SECURITY_GROUP_RULES_QUOTA')
NETWORK_QUOTA = config.get('quotas', 'NETWORK_QUOTA')
SUBNETWORK_QUOTA = config.get('quotas', 'SUBNETWORK_QUOTA')
PORT_QUOTA = config.get('quotas', 'PORT_QUOTA')
ROUTER_QUOTA = config.get('quotas', 'ROUTER_QUOTA')
VIP = config.get('quotas', 'VIP')
POOL = config.get('quotas', 'POOL')
SHARES_QUOTA = config.get('quotas', 'SHARES_QUOTA')
SHARES_GB_QUOTA = config.get('quotas', 'SHARES_GB_QUOTA')
SHARES_SNAPSHOT_QUOTA = config.get('quotas', 'SHARES_SNAPSHOT_QUOTA')
SHARES_SNAPSHOT_GB_QUOTA = config.get('quotas', 'SHARES_SNAPSHOT_GB_QUOTA')
SHARES_NETWORKS_QUOTA = config.get('quotas', 'SHARES_NETWORKS_QUOTA')

logger_.debug("USERNAME:%s" % usr)
logger_.debug("TENANT:%s" % admin_tenant_name)
logger_.debug("URL:%s" % keystone_url)
logger_.debug("CH_URL:%s" % chargeback_url)
logger_.debug("PORTAL_URL:%s" % portal_url)
logger_.debug("compute_url:%s" % compute_url)
logger_.debug("volume_url:%s" % volume_url)
logger_.debug("network_url:%s" % network_url)
logger_.debug("manila_url:%s" % manila_url)

logger_.debug("WHMCS_USERNAME:%s" % whmcs_usr)
logger_.debug("WHMCS_PASSWORD:%s" % whmcs_password)
logger_.debug("WHMCS_URL:%s" % whmcs_url)
logger_.debug("REGEXP:%s" % regexp)
logger_.debug("MAIL_SERVER:%s" % mail_server)
logger_.debug("MAIL_USERNAME:%s" % mail_username)
logger_.debug("MAIL_BCC:%s" % mail_bcc)
logger_.debug("MAIL_FROM:%s" % mail_from)
logger_.debug("TEMPLATE_PORTAL_URL:%s" % template_portal_url)
logger_.debug("TEMPLATE_SUBJECT_ES:%s" % template_subject_es)
logger_.debug("TEMPLATE_SUBJECT_EN:%s" % template_subject_en)
logger_.debug("TEMPLATE_FILE_ES:%s" % template_file_es)
logger_.debug("TEMPLATE_FILE_EN:%s" % template_file_en)

tenant_regexp_ = re.compile(regexp)
whmcs_password_md5 = hashlib.md5(whmcs_password).hexdigest()

total = len(sys.argv)
cmdargs = str(sys.argv)
passw = str(sys.argv[1])

whmcsObj = WHMCS(whmcs_url, whmcs_usr, whmcs_password_md5)
orders = whmcsObj.getPendingOrders()
if int(orders['totalresults']) > 0:
    keystoneObj = Keystone(keystone_url, usr, passw, admin_tenant_name)
    portalObj = Portal(portal_url)
    databaseObj = PortalDb(database_server, database_username, database_password, schema=database_schema)
    for order in orders['orders']['order']:
        pending_order = order
        userId = pending_order['userid']
        serviceId = pending_order['lineitems']['lineitem'][0]['relid']
        product = whmcsObj.getClientProducts(userId, serviceId)
        user = whmcsObj.getUser(userId)
        language = user['language']
        email = user['email']
        if len(language) == 0:
            language = whmcs_language
        tenants = keystoneObj.getTenants()
        tarray = []
        for t in tenants["tenants"]:
            if tenant_regexp_.match(t["name"]):
                if not t["enabled"]:
                    tarray.append(t["name"])
        tenants_available = sorted(tarray)
        if len(tenants_available) > 0:
            tenant_available = tenants_available[0]
            print tenant_available
            print email
            try:
                new_password = ''.join(
                    random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits) for _ in range(12))
                new_user = keystoneObj.create_user(email, new_password, email)
                new_user_id = new_user['id']
                new_tenant = keystoneObj.getTenant(tenant_available)
                new_tenant_id = new_tenant['id']
                for role in default_user_roles:
                    keystoneObj.grant_role_to_user(new_tenant_id, new_user_id, role)
                new_tenant['enabled'] = True
                keystoneObj.update_tenant(new_tenant)
                portalObj.fake_login(email, new_password, 'local')
                databaseObj.updateEmailByUsernameAndCloud(email, email, 'local', language)

                novaObj = Nova(keystoneObj.getToken(), compute_url)
                cinderObj = Cinder(keystoneObj.getToken(), volume_url)
                neutronObj = Neutron(keystoneObj.getToken(), network_url)
                manilaObj = Manila(keystoneObj.getToken(), manila_url)

                novaObj.set_compute_quotas(new_tenant_id, CORES_QUOTA, RAM_QUOTA, INSTANCES_QUOTA,
                                           KEY_PAIRS_QUOTA, FLOATING_IPS_QUOTA, SECURITY_GROUPS_QUOTA,
                                           SECURITY_GROUP_RULES_QUOTA,
                                           METADATA_ITEMS_QUOTA, INJECTED_FILES_QUOTA)
                cinderObj.set_volume_quotas(new_tenant_id, VOLUMES_QUOTA, VOL_GB_QUOTA, SNAPSHOT_QUOTA)
                neutronObj.set_network_quotas(new_tenant_id, NETWORK_QUOTA, SUBNETWORK_QUOTA, ROUTER_QUOTA,
                                              FLOATING_IPS_QUOTA,
                                              PORT_QUOTA,
                                              SECURITY_GROUPS_QUOTA, SECURITY_GROUP_RULES_QUOTA, VIP, POOL)
                manilaObj.set_manila_quotas(new_tenant_id, SHARES_QUOTA, SHARES_GB_QUOTA, SHARES_SNAPSHOT_QUOTA,
                                            SHARES_SNAPSHOT_GB_QUOTA, SHARES_NETWORKS_QUOTA)

                emailObj = Email(mail_username, mail_password, mail_from, mail_bcc, mail_server)
                templateObj = TemplateText(template_folder)
                country = language
                emails = []
                emails.append(email)
                subj = template_subject_en
                template_file = template_file_en
                if country.lower() == "es":
                    subj = template_subject_es
                    template_file = template_file_es
                msg = templateObj.substitute(template_file, {'portal': template_portal_url, 'username': email,
                                                             'tenant': tenant_available, 'password': new_password})
                emailObj.send(emails, subj, msg)
                whmcsObj.acceptOrder(serviceId)
                options = OrderedDict([("Portal", portal_url), ("Tenant ID", tenant_available)])
                whmcsObj.updateClientProductConfigOptions(serviceId, status='Active', configoptions=options)
            except Exception as ex:
                print ex
