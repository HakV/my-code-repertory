"""H3C CAS Client."""

import json
import requests
import six
import time
from urllib import urlencode

from oslo_config import cfg
from oslo_log import log as logging

from egis import exception
from egis.i18n import _LE


LOG = logging.getLogger(__name__)
_SESSION = None

REQUEST_OPT = [
    cfg.IntOpt('request_h3cas_timeout',
               default=180,
               help='Request h3c cas rest api timeout.'),
]

CONF = cfg.CONF
CONF.register_opts(REQUEST_OPT, 'virt')

H3CCAS_RES_MAP = {
    'auth': '/cas/spring_check',
    'host_tree': '/cas/tree/getHostList',
    'hosts': '/cas/casrs/host',
    'host': '/cas/casrs/host/id/{host_id}',
    'vswitchs': '/cas/casrs/host/id/{host_id}/vswitch',
    'vswitch': '/cas/casrs/host/id/{host_id}/vswitch/{vswitch_id}',
    'network_templates': '/cas/casrs/profile/',
    'network_template': '/cas/casrs/profile/{profile_id}',
    'servers': '/cas/casrs/host/id/{host_id}/vm',
    'server': '/cas/casrs/vm/{server_id}',
    'server_create': '/cas/domain/add',
    'server_delete': '/cas/domain/{server_id}/1',
    'server_start': '/cas/domain/{server_id}/start',
    'server_stop': '/cas/domain/{server_id}/close',
    'server_restart': '/cas/domain/{server_id}/restart',
    'server_restore': '/cas/restore/vm',
    'server_backup': '/cas/backupStrategy/vmbackup',
    'server_backup_trees': '/cas/backupStrategy/{server_id}/backupFileTree',
    'vnc': '/cas/casrs/vmvnc/vnc/{server_id}',
    'host_initiatorname': '/cas/host/{host_id}/queryHostInitiatorName',
    'storage_pools': '/cas/casrs/storage/pool?hostId={host_id}',
    'storage_pool_create': '/cas/storage/pool/add',
    'storage_pool_delete': '/cas/storage/host/storagepool',
    'storage_pool_start':
        '/cas/storage/host/{host_id}/storagepool/{stor_pool_name}/start',
    'storage_pool_stop':
        '/cas/storage/host/{host_id}/storagepool/{stor_pool_name}/stop',
    'task_message': '/cas/casrs/message/{msg_id}'}

AUTO_MIGRATE = 1
CPU_CORE_NUMBERS = 1
CPU_NUMBERS = 2
CPU_SCHEDULING_PRIORITY = 1024
IO_SCHEDULING_PRIORITY = 500

CAS_REST_REQ_TIMEOUT = 120


class H3CasClient(object):
    """Client of H3C CAS."""

    def __init__(self, auth_url, username, password, allow_401=True):
        self.allow_401 = allow_401
        self.url = auth_url
        self.auth_param = {'encrypt': False, 'lang': 'cn',
                           'name': username, 'password': password}

        # To redure login time, verified session will be used.
        global _SESSION
        if _SESSION:
            self.session = _SESSION
        else:
            self.session = _SESSION = requests.session()
            self._login()

    def _url_combiner(self, url_list):
        """Integrate request url."""
        return ''.join(url_list)

    def _login(self):
        """Try to login H3C CAS."""

        login_url = self._url_combiner([self.url, H3CCAS_RES_MAP['auth']])
        try:
            self._req(login_url, 'post', params=self.auth_param)
        except Exception as err:
            LOG.exception(
                _LE("Failed to login the H3C CAS, "
                    "detailed error as %s"),
                six.text_type(err))
            raise exception.ConnectionUnauthorized(
                auth_url=login_url,
                auth_user=self.auth_param['name'])

    def _req(self, url, method, params=None, data=None, headers=None,
             url_encode=None, raw=None, slug=None):
        """A Wrapper method for send request."""

        default_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'}
        if headers and type(headers) is dict:
            default_headers.update(headers)

        if not url_encode:
            req_data = json.dumps(data)
        elif url_encode and data:
            req_data = urlencode(data)
        else:
            req_data = None

        try:
            do_req = self.session.__getattribute__(method)
        except Exception as err:
            LOG.exception(
                _LE("Failed to get the %(method)s from session object, "
                    "detailed error as %(err)s."),
                {'method': method, 'err': six.text_type(err)})
            raise exception.HTTPMethodNotFound(method=method)

        try:
            res = do_req(url, params=params, data=req_data,
                         headers=default_headers,
                         timeout=CONF.virt.request_h3cas_timeout)
        except Exception as err:
            LOG.exception(
                _LE("Failed to send the http request %(url)s, "
                    "params as %(params)s, data as %(data)s, "
                    "headers as %(headers)s, detailed error as %(err)s"),
                {'url': url, 'params': params, 'data': data,
                 'headers': headers, 'err': six.text_type(err)})
            raise exception.SendHTTPRequestError()

        if res.status_code == 401 and self.allow_401:
            # Unauthorized.
            self._login()
            res = do_req(url, params=params, data=req_data,
                         headers=default_headers,
                         timeout=CONF.virt.request_h3cas_timeout)
        elif res.status_code == 401 and not self.allow_401:
            raise exception.AuthorizationFailure()
        elif res.status_code == 400 or \
                (res.status_code >= 402 and res.status_code <= 600):
            error_code = res.status_code
            error_content = res.content
            LOG.exception(
                _LE("Failed to request h3c cas rest api %(url)s, "
                    "error code %(error_code)s, detailed error info "
                    "as %(content)s"),
                {'url': url,
                 'error_code': error_code,
                 'content': error_content})
            raise exception.H3CasRequestError(url=url)
        return self._handle_res(res, raw, slug)

    def _handle_res(self, res, raw, slug):
        """Handle response of each http request."""
        def _parse(res, slug):
            res_json = res.json()
            if slug not in res_json.keys():
                return res_json
            return res_json[slug]
        if raw:
            return res
        if type(res) == dict:
            return res
        if slug:
            return _parse(res, slug)
        return res.json()

    def _rest_call(self, req_url, method='get', params=None,
                   data=None, headers=None, url_encode=False):
        """Call h3c cas rest api."""

        # Check the HTTP request method.
        if method not in ['get', 'post', 'put', 'delete']:
            LOG.error(_LE('HTTP method %s not found.'), method)
            raise exception.HTTPMethodNotFound(method=method)

        try:
            resp = self._req(req_url, method, params, data,
                             headers, url_encode, slug=None, raw=False)
        except Exception as err:
            LOG.exception(
                _LE("Failed the request the h3c cas rest api %(url)s ,"
                    "detailed error as %(err)s"),
                {'url': req_url, 'err': six.text_type(err)})
            raise exception.H3CasRequestError(url=req_url)
        return resp

    def clear_session(self):
        try:
            self.session.close()
            global _SESSION
            _SESSION = None
        except Exception:
            LOG.exception(
                _LE('Failed to clear session object %s'), self.session)
            raise exception.ClearSessionError()

    def host_tree_get(self):
        req_url = self._url_combiner([self.url, H3CCAS_RES_MAP['host_tree']])
        return self._rest_call(req_url, method='get')

    def hosts_get_all(self):
        req_url = self._url_combiner([self.url, H3CCAS_RES_MAP['hosts']])
        return self._rest_call(req_url, method='get')

    def host_get_info(self, host_id):
        """Get host detailed information with host id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['host'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def vswitchs_get_all(self, host_id):
        """Get all the vSwitchs with host id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['vswitchs'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def vswitch_get_info(self, host_id, vswitch_id):
        """Get vSwitch detailed information with host id and vSwitch id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['vswitch'].format(host_id=host_id,
                                             vswitch_id=vswitch_id)])
        return self._rest_call(req_url, method='get')

    def network_templates_get_all(self):
        """Get all the network templates."""
        req_url = self._url_combiner([self.url,
                                      H3CCAS_RES_MAP['network_templates']])
        return self._rest_call(req_url, method='get')

    def network_template_get_info(self, profile_id):
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['network_template'].format(profile_id=profile_id)])
        return self._rest_call(req_url, method='get')

    def host_initiatorname_get(self, host_id):
        """Get the initiator iqn name via host_id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['host_initiatorname'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def storage_pools_get_all(self, host_id):
        """Get all the storage pools with host id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['storage_pools'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def storage_pool_create(self, stor_pool_info):
        """Create the storage pool with stor_pool_info.

            e.g.1: iSCSI device
                stor_pool_info = {
                    'fsName':
                        'iqn.2013-09.com.prophetstor:flexvisor.53087136ddfa',
                    'hostId': '1',
                    'name': 'drp-iscsi',
                    'path': '/dev/disk/by-path',
                    'rsFsLunInfoList': [],
                    'srcHost': '200.21.110.3',
                    'srcPath':
                        'iqn.2013-09.com.prophetstor:flexvisor.53087136ddfa',
                    'title': 'drp-scsi',
                    'type': 'iscsi'}

            e.g.2: NFS device
                stor_pool_info = {
                    'hostId': '9',
                    'hostIp': '200.21.18.100',
                    'name': 'drp-nfs'
                    'path': '/vms/drp-nfs'
                    'remoteDir': '/home/drp-server-nfs'
                    'rsFsLunInfoList': []
                    'title': 'drp-nfs'
                    'type': 'netfs'}
        """

        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['storage_pool_create']])
        return self._rest_call(req_url, method='post', data=stor_pool_info)

    def storage_pool_destroy(self, host_id, stor_pool_name):
        """Delete storage pool with host id and storage pool name."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['storage_pool_delete']])
        req_params = {'hostId': host_id, 'poolName': stor_pool_name}
        return self._rest_call(req_url, method='delete', params=req_params)

    def storage_pool_start(self, host_id, stor_pool_name):
        """Activate storage pool with host id and storage pool name."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['storage_pool_start'].format(
                host_id=host_id,
                stor_pool_name=stor_pool_name)])
        return self._rest_call(req_url, method='put')

    def storage_pool_stop(self, host_id, stor_pool_name):
        """Close storage pool with host id and storage pool name."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['storage_pool_stop'].format(
                host_id=host_id,
                stor_pool_name=stor_pool_name)])
        return self._rest_call(req_url, method='put')

    def servers_get_all(self, host_id):
        """Get all the servers via host_id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['servers'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def server_get_info(self, server_id):
        """Get server detalied information with server id."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['server'].format(server_id=server_id)])
        return self._rest_call(req_url, method='get')

    def server_create(self, create_info):
        """Create server with create_info.

            e.g.1: Boot via block device (iSCSI)
                create_info = {
                    'name': 'h3c_cas_recovery',
                    'cluster_id': 1,
                    'host_id': 1,
                    'host_pool_id': 1,
                    'cpu_num': 2,
                    'memory': '4096',
                    'boot_drive': 'vga',
                    'networks': [{
                        'name': 'vswitch0',
                        'profileId': 1,
                        'profileName': 'Default',
                        'vswitchId': 1}]
                    'storages': [{
                        'type': 'block',
                        'driveType': 'dos',
                        'storeFile':
                            '/dev/disk/by-path/ip-200.21.110.3:'
                            '3260-iscsi-iqn.2013-09.com.prophetstor:'
                            'flexvisor.53087136ddfa-lun-0'}]
                }

            e.g.2: Boot via file (NFS)
                create_info = {
                    'name': 'h3c_cas_recovery',
                    'cluster_id': 1,
                    'host_id': 1,
                    'host_pool_id': 1,
                    'cpu_num': 2,
                    'memory': '4096',
                    'boot_drive': 'vga',
                    'networks': [{
                        'deviceModel': 'virtio',
                        'name': 'vswitch0',
                        'profileId': 1,
                        'profileName': 'Default',
                        'vswitchId': 1}]
                    'storages': [{
                        'targetBus': 'virtio',
                        'type': 'file',
                        'driveType': 'raw',
                        'storeFile':
                            '/vms/aaa/20170224T100502-2000-backup-flat.vmdk'}]
                }
        """
        def_network_params = {'driver': 'vhost',
                              'mode': 'veb'}
        def_storage_params = {'cache': 'directsync',
                              'capacity': 10240,
                              'diskDevice': 'disk'}
        for network in create_info['networks']:
            network.update(def_network_params)
        for storage in create_info['storages']:
            storage.update(def_storage_params)

        # FIXME(Fan Guiju): Using global variable to replace the numbers.
        server_body = {
            'autoMem': 0,
            'autoMigrate': AUTO_MIGRATE,
            'autoTools': True,
            'blkiotune': IO_SCHEDULING_PRIORITY,
            'clusterId': create_info['cluster_id'],
            'cpu': create_info['cpu_num'],
            'cpuCore': CPU_CORE_NUMBERS,
            'cpuGurantee': 0,
            'cpuMode': 'custom',
            'cpuQuotaUnit': 'MHz',
            'cpuShares': CPU_SCHEDULING_PRIORITY,
            'cpuSocket': CPU_NUMBERS,
            'description': 'Recovery from DRCloud',
            'devList': [],
            'drive': create_info['boot_drive'],
            'hostId': create_info['host_id'],
            'hostPoolId': create_info['host_pool_id'],
            'maxCpuSocket': 12,
            'memory': create_info['memory'],
            'memoryInit': 4,
            'memoryLocked': '0',
            'memoryPriority': '0',
            'memoryUnit': 'GB',
            'networks': create_info['networks'],
            # FIXME(Fan Guiju):Get the system type from payload.
            'osBit': 'x86_64',
            'osVersion': 'Other Linux(64-bit)',
            'system': 1,
            'storages': create_info['storages'],
            'title': create_info['name'],
            'viewType': 'vnc'}
        req_url = ''.join([self.url, H3CCAS_RES_MAP['server_create']])
        return self._rest_call(req_url, data=server_body, method='post')

    def server_destroy(self, server_id, server_name):
        """Destroy server with server id and server name."""
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['server_delete'].format(server_id=server_id)])
        destroy_params = {'isWipeVolume': True,
                          'data': 1,
                          'isWipeVolume': True,
                          'title': server_name,
                          'type': 1,
                          'vmId': server_id}
        return self._rest_call(req_url, params=destroy_params, method='delete')

    def server_power_on(self, server_id):
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['server_start'].format(server_id=server_id)])
        return self._rest_call(req_url, method='put')

    def server_power_off(self, server_id):
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['server_stop'].format(server_id=server_id)])
        return self._rest_call(req_url, method='put')

    def server_restart(self, server_id):
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['server_restart'].format(server_id=server_id)])
        return self._rest_call(req_url, method='put')

    def server_backup(self, server_id, serverbackup_name, serverbackup_type,
                      backup_dest_dir, remote_copy_type=0):
        """Backup the h3cas virtualmachine via backup_values as below.

           eg. backup_values = {
                   backupName: "centos7_backup_4",
                   backupType: "1",
                   directory: "/mnt/h3cas_backup",
                   isCompression: 1,
                   isMd5Check: 0,
                   keepTimes: "30",
                   readRatio: 500,
                   storeMode: 0,
                   tmpDir: "/vms/vmbackuptmp",
                   type: 0,
                   vmId: "12",
                   writeRatio: 500
               }
        """
        backup_params = {
            'vmId': server_id,
            'backupName': serverbackup_name,
            'backupType': serverbackup_type,
            'directory': backup_dest_dir,
            'type': remote_copy_type,
            'isCompression': 1,
            'isMd5Check': 0,
            'keepTimes': '30',
            'writeRatio': 500,
            'readRatio': 500,
            'storeMode': 0,
            'tmpDir': '/vms/vmbackuptmp'}
        req_url = self._url_combiner([self.url,
                                      H3CCAS_RES_MAP['server_backup']])
        return self._rest_call(req_url, method='post', data=backup_params)

    def server_backup_trees_get_all(self, server_id):
        """Get all the backup information of h3cas virtualmachine.

           response as below:
               {
                   "state": 0,
                   "errorCode": 0,
                   "successMessage": null,
                   "failureMessage": null,
                   "data":[
                       {
                           "targetAddr": null,
                           "location": "local_directory: /mnt/h3cas_backup",
                           "children": [
                           ],
                           "type": "cp",
                           "password": null,
                           "mode": 10,
                           "size": 565.4296875,
                           "id": 41,
                           "isDelete": 0,
                           "parentId": 0,
                           "time": 1494426873000,
                           "directory": "/mnt/h3cas_backup",
                           "domainId": 12,
                           "name": "centos7_backup_0",
                           "isLeaf": 0,
                           "userName": null
                       }
                   ],
                   "success": true
               }
        """
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['server_backup_trees'].format(server_id=server_id)])
        return self._rest_call(req_url, method='get')

    def server_restore(self, backup_id, backup_dir, backup_time,
                       backup_type='cp', username=None, password=None,
                       target_ipaddr=None):
        """Restore the h3cas virthalmachine via restore_values as below.

            e.g. restore_values = {
                     backupId: 43,
                     directory: "/mnt/h3cas_backup",
                     entryType: "VIRTUAL_HOST",
                     isForce: false,
                     userName: null,
                     password: null,
                     targetAddr: null,
                     time: 1494428388000,
                     tmpDir: "/vms/vmbackuptmp",
                     type: "cp",
                 }
        """
        restore_params = {
            'backupId': backup_id,
            'directory': backup_dir,
            'entryType': 'VIRTUAL_HOST',
            'isForce': False,
            'userName': username,
            'password': password,
            'targetAddr': target_ipaddr,
            'time': backup_time,
            'tmpDir': '/vms/vmbackuptmp',
            'type': backup_type}
        req_url = self._url_combiner([self.url,
                                      H3CCAS_RES_MAP['server_restore']])
        return self._rest_call(req_url, method='put', data=restore_params)

    def vnc_get_info(self, server_id):
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['vnc'].format(server_id=server_id)])
        return self._rest_call(req_url, method='get')

    def task_message_get_info(self, msg_id):
        req_url = self._url_combiner([
            self.url,
            H3CCAS_RES_MAP['task_message'].format(msg_id=msg_id)])
        return self._rest_call(req_url, method='get')

    def wait_for_task(self, req_result):
        if req_result.get('success'):
            msg_id = req_result['data']
            timeout = CAS_REST_REQ_TIMEOUT
            while timeout >= 0:
                task_info = self.task_message_get_info(msg_id)
                if task_info['completed'] and task_info['progress'] == '100':
                    return task_info
                timeout -= 2
                time.sleep(2)
            raise
        raise


if __name__ == '__main__':
    h3cas_cli = H3CasClient(auth_url='http://200.21.18.100:8080',
                            username='admin',
                            password='admin')
    hosts = h3cas_cli.hosts_get_all()
    servers = h3cas_cli.servers_get_all(host_id=hosts['host']['id'])
    server_backup_trees = h3cas_cli.server_backup_trees_get_all(
        server_id=servers['domain']['id'])
    backup_info = server_backup_trees['data'][0]['children'][3]
    # Restore the h3cas virtualmachine.
    req_result = h3cas_cli.server_restore(backup_id=backup_info['id'],
                                          backup_dir=backup_info['directory'],
                                          backup_time=backup_info['time'])
    task_result = h3cas_cli.wait_for_task(req_result)
    print task_result
