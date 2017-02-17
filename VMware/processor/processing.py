# Copyright 2016 Beijing Huron Technology Co.Ltd.
#
# Authors: Fan Guiju <fanguiju@hihuron.com>
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from urlparse import urlparse
from uuid import uuid4

from oslo_log import log as logging

from egis.virt.base import api as core_api
from egis.virt.vmware.collector import collecting


LOG = logging.getLogger(__name__)


class DataProcessor(object):
    """Vmware information handle."""

    def __init__(self, context, vmware_connect_id):
        self.collector = collecting.DataCollector(context, vmware_connect_id)
        self.context = context
        self.vmware_connect_id = vmware_connect_id
        self.core_api = core_api.API()

    def to_dict(self, **kwargs):
        dict_ref = {}
        for key, value in kwargs.items():
            dict_ref[key] = value
        return dict_ref

    def _get_vmware_network_info(self, host, port_group_name):

        LOG.debug("Get vmware network info for standard port group %(pg)s "
                  "from host %(host)s.",
                  {'pg': port_group_name, 'host': host})

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

    def vmware_host_list(self, context):
        """Get the vmware esxi hypervisor information."""

        # Get hosts uuid from DB.
        filters = {'connection_uuid': self.vmware_connect_id,
                   'type': 'vmware'}
        hosts_from_db = self.core_api.hyper_host_get_all(context,
                                                         filters=filters)
        db_hosts = [host.get('name') for host in hosts_from_db]

        # Get hosts uuid from VMware.
        vmware_hosts = []
        hosts_from_vmware = self.collector.managed_object_get('HostSystem')
        hosts_from_vmware = hosts_from_vmware.objects
        for host in hosts_from_vmware:
            vmware_hosts.append(host.obj.value)

        # Compare the two List object to find different hosts.
        host_need_delete = [host for host in hosts_from_db if
                            host.get('name') not in vmware_hosts]
        host_need_create = [host for host in hosts_from_vmware if
                            host.obj.value not in db_hosts]

        for host in host_need_delete:
            self.core_api.hyper_host_delete(context, host.id)
            network_need_delete = self.core_api.hyper_network_get_all(
                context,
                filters={'constraints': 'hyper_host:' + host.id})
            for network in network_need_delete:
                self.core_api.hyper_network_delete(context, network.id)

        values_list = network_list = []
        if host_need_create:
            values_list, network_list = self.get_esxi_hypervisors_values(
                host_need_create)
        return (values_list, network_list)

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

                    # FIXME (Fan Guiju): Get values of all the fields.
                    standard_network_values = {
                        'iface_name': iface_name,
                        'physical_name': None,
                        'net_type': 'standard_network',
                        'vlan_id': vlan_id,
                        'cidr': None,
                        'managed': False,
                        'type': 'vmware',
                        'hyper_id': hyper_id,
                        'constraints': 'hyper_host:' + esxi_hypervisor_id,
                        'connection_uuid': self.vmware_connect_id}
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
                        'connection_uuid': self.vmware_connect_id,
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
                           'hyper_id': hyper_id,
                           'connection_uuid': self.vmware_connect_id}

            host_values_list.append(host_values)
            # FIXME(Fan Guiju): Merge elements from network_values_list
            #                   with the same value.
        return host_values_list, network_values_list
