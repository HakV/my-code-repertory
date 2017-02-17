from urlparse import urlparse
from uuid import uuid4

from collector import collecting


class DataProcessor(object):
    """Vmware information handle."""

    def __init__(self, auth_url, username, password):
        self.collector = collecting.DataCollector(auth_url, username, password)

    def to_dict(self, *args, **kwargs):
        dict_ref = {}
        for key, value in kwargs.items():
            dict_ref[key] = value
        return dict_ref

    def _get_vmware_network_info(self, host, port_group_name):
        # Get the vlan_id with port group.
        port_group_object = self.collector.\
            manager_properties_dict_get(host.obj,
                                        "config.network.portgroup")
        if not port_group_object:
            vlan_id = 'None'
        port_group = port_group_object['config.network.portgroup'].\
            HostPortGroup
        for pg in port_group:
            if pg.spec.name == port_group_name:
                vlan_id = pg.spec.vlanId

        return vlan_id

    def _get_vmware_dvsnetwork_info(self, network_summary,
                                    dvpg_cfg):
        dvspg_key = network_summary['summary'].network.value

        # Get overall networks
        dvpgs = self.collector.\
            managed_object_get('DistributedVirtualPortgroup')
        for dvpg in dvpgs.objects:
            if dvpg_cfg['config'].key != dvspg_key:
                continue

            vdvs_config = self.collector.manager_properties_dict_get(
                dvpg_cfg['config'].distributedVirtualSwitch, 'config')

            dvs_uuid = vdvs_config['config'].uuid
            dvspg_key = dvpg_cfg['config'].key
            dvspg_name = dvpg_cfg['config'].name

            vlan = dvpg_cfg['config'].defaultPortConfig.vlan
            vlan_type = vlan_id = None
            if str(type(vlan)) == \
                    "<class 'suds.sudsobject."\
                    "VmwareDistributedVirtualSwitchTrunkVlanSpec'>":
                vlan_type = 'TrunkVlan'
                vlan_id = ''.join(['[', str(vlan.vlanId[0].start), ',',
                                   str(vlan.vlanId[0].end), ']'])

            elif str(type(vlan)) == \
                    "<class 'suds.sudsobject."\
                    "VmwareDistributedVirtualSwitchVlanIdSpec'>":
                vlan_type = 'VlanId'
                vlan_id = vlan.vlanId

            elif str(type(vlan)) == \
                    "<class 'suds.sudsobject."\
                    "VmwareDistributedVirtualSwitchPvlanSpec'>":
                vlan_type = 'Pvlan'
                vlan_id = vlan.pvlanId

            vmware_dvsnetwork_dict = self.to_dict(
                id=str(uuid4()),
                is_dvs=True,
                dvspg_name=dvspg_name,
                dvspg_key=dvspg_key,
                dvs_uuid=dvs_uuid,
                vlan_type=vlan_type,
                vlan_id=vlan_id)
            return vmware_dvsnetwork_dict


    def get_esxi_hypervisors_values(self, hosts):
        host_values_list = []
        network_values_list = []
        for host in hosts:
            LOG.debug("Get the info of vmware esxi hypervisor %s", host)

            host_name = host.obj.value
            # Get esxi host summary
            host_summary = self.collector.manager_properties_dict_get(
                host.obj, 'summary')
            host_summary = host_summary.get('summary')

            # Get the sizes of esxi hypervisor memory
            if not host_summary.quickStats or\
                    not host_summary.quickStats.overallMemoryUsage:
                memory_used = None
            else:
                memory_used = host_summary.quickStats.overallMemoryUsage

            # Get the esxi hardware uuid
            hyper_id = host_summary.hardware.uuid

            # Get the esxi host whether in vcenter and display_name
            # If YES: hostname equal to host ipaddr
            # If NO: hostname equal to FQDN,
            #        need to get the host ipaddr from vmware connect.
            try:
                int(str(host_summary.config.name).split('.')[0])
                host_ipaddr = host_display_name = host_summary.config.name
                whether_is_vcenter = True
            except ValueError:
                vmware_connect_info = self.core_api.hyper_connection_get(
                    self.context,
                    self.vmware_connect_id)
                auth_url = vmware_connect_info.get('auth_url')
                # FIXME(Fan Guiju): Convert host name to ipaddress
                host_ipaddr = urlparse(auth_url).hostname
                host_display_name = host_summary.config.name
                whether_is_vcenter = False

            update_body = {'metadata': {'is_vcenter': whether_is_vcenter}}
            self.core_api.hyper_connection_update(
                self.context,
                self.vmware_connect_id,
                update_body)

            # Get vmware network information
            networks = self.collector.\
                manager_properties_dict_get(host.obj,
                                            'network')

            # Setup vmware exsi uuid
            esxi_hypervisor_id = str(uuid4())

            # If don't setup the network on esxi hypervisor, just pass
            for network in networks['network'][0]:
                # Get the network summary
                network_summary = self.collector.\
                    manager_properties_dict_get(network,
                                                'summary')

                if network_summary['summary'].network._type == 'Network':
                    # This network is standard network object
                    iface_name = network_summary['summary'].name

                    vlan_id = self._get_vmware_network_info(host,
                                                            iface_name)

                    standard_network_values = {
                        'iface_name': iface_name,
                        'physical_name': None,
                        'net_type': 'standard_network',
                        'vlan_id': vlan_id,
                        'cidr': None,
                        'managed': False,
                        'type': 'vmware',
                        'hyper_id': hyper_id,
                        'constraints': 'hyper_host:' + esxi_hypervisor_id}
                    network_values_list.append(standard_network_values)

                elif network_summary['summary'].\
                        network._type == 'DistributedVirtualPortgroup' \
                        and whether_is_vcenter:
                    dvpg_cfg = self.collector.manager_properties_dict_get(
                        network,
                        'config')
                    # Ensure the portgroup not a uplink_portgroup
                    if not dvpg_cfg['config'].defaultPortConfig.\
                            uplinkTeamingPolicy.uplinkPortOrder.inherited:
                        continue
                    # get vmware_dvsnetwork_lsit
                    vmware_dvsnetwork_info = \
                        self._get_vmware_dvsnetwork_info(network_summary,
                                                         dvpg_cfg)

                    dvs_network_values = {
                        'iface_name': vmware_dvsnetwork_info.get('dvspg_name'),
                        'physical_name': None,
                        'net_type': 'distributed_network',
                        'vlan_id': vmware_dvsnetwork_info.get('vlan_id'),
                        'cidr': None,
                        'managed': False,
                        'type': 'vmware',
                        'hyper_id': hyper_id,
                        'constraints': 'hyper_host:' + esxi_hypervisor_id,
                        'metadata': {
                            'vlan_type':
                                vmware_dvsnetwork_info.get('vlan_type'),
                            'dvspg_key':
                                vmware_dvsnetwork_info.get('dvspg_key'),
                            'dvs_uuid':
                                vmware_dvsnetwork_info.get('dvs_uuid')}}

                    network_values_list.append(dvs_network_values)

            host_values = {'id': esxi_hypervisor_id,
                           'display_name': host_display_name,
                           'name': host_name,
                           'ip': host_ipaddr,
                           'cores': host_summary.hardware.numCpuCores,
                           'mem_used': int(memory_used) * 1024 * 1024,
                           'mem_total': host_summary.hardware.memorySize,
                           'type': 'vmware',
                           'hyper_id': hyper_id}

            host_values_list.append(host_values)
        return host_values_list, network_values_list
