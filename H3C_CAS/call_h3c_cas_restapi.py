import requests
import json
from urllib import urlencode
from time import sleep


_SESSION = None
TIMEOUT = 60
H3CCAS_RES_MAP = {
    'auth': '/cas/spring_check',
    'hosts': '/cas/casrs/host',
    'host': '/cas/casrs/host/id/{host_id}',
    'vswitchs': '/cas/casrs/host/id/{host_id}/vswitch',
    'vswitch': '/cas/casrs/host/id/{host_id}/vswitch/{vswitch_id}',
    'share_storages': '/cas/casrs/host/id/{host_id}/storage',
    'create_server': '/cas/domain/add',
    'servers': '/cas/casrs/host/id/{host_id}/vm',
    'server': '/cas/casrs/vm/{server_id}',
    'start_server': '/cas/domain/{server_id}/start',
    'delete_server': '/cas/domain/{server_id}/1',
    'vnc': '/cas/casrs/vmvnc/vnc/{server_id}'}


class H3cCasClient(object):
    """Client of H3C CAS."""

    def __init__(self, host, port, username, password):
        self.url = 'http://%s:%s' % (host, port)
        self.auth_param = {'encrypt': False, 'lang': 'cn',
                           'name': username, 'password': password}

        # To redure login time, verified session will be used.
        global _SESSION
        if _SESSION:
            self.session = _SESSION
        else:
            _SESSION = self.session = requests.session()
            self._login()

    def _login(self):
        """Try to login H3C CAS."""
        login_url = '%s%s' % (self.url, H3CCAS_RES_MAP['auth'])

        try:
            self._req(login_url, 'post', params=self.auth_param)
        except Exception:
            raise

    def _req(self, url, method, params=None, data=None, headers=None,
             url_encode=None, slug=None, raw=None):
        """A Wrapper method for send request."""

        if not url:
            raise

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
        except Exception:
            raise

        try:
            res = do_req(url, params=params, data=req_data,
                         headers=default_headers, timeout=TIMEOUT)
            print res
            print res.content
            if res.status_code == 403:
                self._login()
                res = do_req(url, params=params, data=req_data,
                             headers=default_headers, timeout=TIMEOUT)
            elif res.status_code == 400:
                raise
            return self._handle_res(res, raw, slug)
        except Exception:
            raise

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
        """Call REST API."""

        # Check the HTTP request method.
        if method not in ['get', 'post', 'put', 'delete']:
            raise

        try:
            resp = self._req(req_url, method, params, data,
                             headers, url_encode, slug=None, raw=False)
            return resp
        except Exception:
            raise

    def hosts_get_all(self):
        req_url = ''.join([self.url, H3CCAS_RES_MAP['hosts']])
        return self._rest_call(req_url, method='get')

    def host_get_info(self, host_id=None):
        req_url = ''.join([self.url,
                           H3CCAS_RES_MAP['host'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def vswitchs_get_all(self, host_id):
        req_url = ''.join([self.url,
                           H3CCAS_RES_MAP['vswitchs'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def vswitch_get_info(self, host_id, vswitch_id):
        req_url = ''.join([
            self.url,
            H3CCAS_RES_MAP['vswitch'].format(host_id=host_id,
                                             vswitch_id=vswitch_id)])
        return self._rest_call(req_url, method='get')

    def share_storages_get_all(self, host_id):
        req_url = ''.join([
            self.url,
            H3CCAS_RES_MAP['share_storages'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def create_server(self, host_id, vswitch_id, boot_mode=None):

        server_body = {
            'autoMem': 0,
            'autoMigrate': 0,
            'autoTools': True,
            'blkiotune': 300,
            'clusterId': '',
            'cpu': 2,
            'cpuCore': 1,
            'cpuGurantee': 0,
            'cpuMode': 'custom',
            'cpuQuotaUnit': 'MHz',
            'cpuShares': 512,
            'cpuSocket': 2,
            'description': 'Just test create via REST API',
            'devList': [],
            'drive': 'cirrus',
            'hostId': host_id,
            'hostPoolId': 1,
            'maxCpuSocket': 12,
            'memory': 4096,
            'memoryInit': 4,
            'memoryLocked': '0',
            'memoryPriority': '0',
            'memoryUnit': 'GB',
            'networks': [{'deviceModel': 'virtio',
                          'driver': 'vhost',
                          'mode': 'veb',
                          'name': 'vswitch0',
                          'profileId': 1,
                          'profileName': 'Default',
                          'vswitchId': vswitch_id}],
            'osBit': 'x86_64',
            'osVersion': 'Ubuntu Linux(64-bit)',
            'storages': [{'cache': 'directsync',
                          'capacity': 10240,
                          'diskDevice': 'disk',
                          'driveType': 'qcow2',
                          'storeFile':
                              '/vms/images/ubuntu_server_1404_x64.qcow2',
                          'targetBus': 'virtio',
                          'type': 'file'}],
            'system': 1,
            'title': 'aju-test-rest-api',
            'viewType': 'vnc'}
        req_url = ''.join([self.url, H3CCAS_RES_MAP['create_server']])
        return self._rest_call(req_url, data=server_body, method='post')

    def servers_get_all(self, host_id):
        req_url = ''.join([self.url,
                           H3CCAS_RES_MAP['servers'].format(host_id=host_id)])
        return self._rest_call(req_url, method='get')

    def server_get_info(self, server_id):
        req_url = ''.join([
            self.url,
            H3CCAS_RES_MAP['server'].format(server_id=server_id)])
        return self._rest_call(req_url, method='get')

    def server_start(self, server_id):
        req_url = ''.join([
            self.url,
            H3CCAS_RES_MAP['start_server'].format(server_id=server_id)])
        return self._rest_call(req_url, method='put')

    def server_destroy(self, server_id, server_name):
        req_url = ''.join([
            self.url,
            H3CCAS_RES_MAP['delete_server'].format(server_id=server_id)])
        destroy_params = {'isWipeVolume': True,
                          'data': 1,
                          'isWipeVolume': True,
                          'title': server_name,
                          'type': 1,
                          'vmId': server_id}
        return self._rest_call(req_url, params=destroy_params, method='delete')

    def vnc_get_info(self, server_id):
        req_url = ''.join([
            self.url,
            H3CCAS_RES_MAP['vnc'].format(server_id=server_id)])
        return self._rest_call(req_url, method='get')


def main():
    cas_client = H3cCasClient(host='200.21.18.100',
                              port='8080',
                              username='admin',
                              password='admin')
    hosts = cas_client.hosts_get_all()
    host_info = cas_client.host_get_info(host_id=hosts['host']['id'])
    vswitchs = cas_client.vswitchs_get_all(host_id=hosts['host']['id'])
    vswitch_info = cas_client.vswitch_get_info(
        host_id=vswitchs['vSwitch']['hostId'],
        vswitch_id=vswitchs['vSwitch']['id'])
    share_storages = cas_client.share_storages_get_all(
        host_id=hosts['host']['id'])
    new_server = cas_client.create_server(host_id=hosts['host']['id'],
                                          vswitch_id=vswitchs['vSwitch']['id'])
    sleep(3)
    servers = cas_client.servers_get_all(host_id=hosts['host']['id'])
    if type(servers['domain']) is list:
        for server in servers['domain']:
            server_info = cas_client.server_get_info(server_id=server['id'])
            start_server_results = cas_client.server_start(
                server_id=server['id'])
            vnc_info = cas_client.vnc_get_info(server_id=server['id'])
            delete_server_results = cas_client.server_destroy(
                server_id=server['id'],
                server_name=server_info['title'])
    elif type(servers['domain']) is dict:
        server = servers['domain']
        server_info = cas_client.server_get_info(
            server_id=server['id'])
        start_server_results = cas_client.server_start(
            server_id=server['id'])
        vnc_info = cas_client.vnc_get_info(server_id=server['id'])
        delete_server_results = cas_client.server_destroy(
            server_id=server['id'],
            server_name=server_info['title'])


if __name__ == '__main__':
    main()
