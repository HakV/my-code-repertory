# Copyright 2017 OpenStack Foundation
# All Rights Reserved.
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

from oslo_vmware import api
from oslo_vmware import exceptions as vexc
from oslo_vmware import vim_util


_SESSION = None

API_RETRY_COUNT = 2
TASK_POLL_INTERVAL = 3
MAX_SINGLE_CALL = 100

VNC_CONFIG_KEY = 'config.extraConfig["RemoteDisplay.vnc.port"]'
BIOS_MODE = 'bios'
EFI_MODE = 'efi'
MAX_NUMBER_OBJECTS_RETURN = 100

VNC_PORT_START = 5600
VNC_PORT_TOTAL = 1000

VIF_MODEL_VIRTIO = 'virtio'
VIF_MODEL_NE2K_PCI = 'ne2k_pci'
VIF_MODEL_PCNET = 'pcnet'
VIF_MODEL_RTL8139 = 'rtl8139'
VIF_MODEL_E1000 = 'e1000'
VIF_MODEL_E1000E = 'e1000e'
VIF_MODEL_NETFRONT = 'netfront'
VIF_MODEL_SPAPR_VLAN = 'spapr-vlan'
VIF_MODEL_SRIOV = 'sriov'
VIF_MODEL_VMXNET = 'vmxnet'
VIF_MODEL_VMXNET3 = 'vmxnet3'


class VMwareClient(object):
    """Client of vSphere."""

    def __init__(self, vsphere_url, username, password):
        """Get the instance of VSphereClient.

        :params vsphere_url: a string of vSphere connection url.
        :type: ``str``
            e.g. 'https://127.0.0.1:443'

        :params username: a string of vSphere login username.
        :type: ``str``

        :params password: a string of vSphere login password.
        :type: ``str``
        """

        vsphere_url = urlparse(vsphere_url)
        self.vsphere_ipaddr = vsphere_url.hostname
        self.vsphere_port = vsphere_url.port
        global _SESSION
        if _SESSION:
            self.session = _SESSION
        else:
            try:
                _SESSION = self.session = api.VMwareAPISession(
                    host=self.vsphere_ipaddr,
                    server_username=username,
                    server_password=password,
                    api_retry_count=API_RETRY_COUNT,
                    task_poll_interval=TASK_POLL_INTERVAL,
                    port=self.vsphere_port)
            except vexc.VimFaultException:
                raise
            except Exception:
                raise

    def _managed_object_get(self, managed_object_type, action='get_objects'):
        """Get managed object of vSphere."""
        try:
            # param: maximum number of objects that should be returned in a
            #        single call = 100
            managed_object = self.session.invoke_api(
                vim_util,
                action,
                self.session.vim,
                managed_object_type,
                MAX_NUMBER_OBJECTS_RETURN)
        except vexc.ManagedObjectNotFoundException:
            raise
        return managed_object

    def _manager_properties_dict_get(self, managed_subobject, propertie):
        """Get the properties of managed sub-object."""
        try:
            manager_properties_dict = self.session.invoke_api(
                vim_util,
                'get_object_properties_dict',
                self.session.vim,
                managed_subobject,
                propertie)
        except Exception:
            raise
        return manager_properties_dict

    def _wait_for_task(self, task_ref):
        """Wait for vCenter task done."""
        try:
            result = self.session.wait_for_task(task_ref)
        except Exception:
            raise
        return result

    def _get_datacenter_obj(self, host_ip):
        """Get Datacenter Managed object via ESXi Host Ipaddress."""
        datacenters = self._managed_object_get('Datacenter')
        for datacenter in datacenters.objects:
            host_folder = self._manager_properties_dict_get(datacenter.obj,
                                                            'hostFolder')
            host_folder_obj = host_folder.get('hostFolder')
            if not host_folder_obj:
                continue

            hosts = self._manager_properties_dict_get(host_folder_obj,
                                                      'childEntity')
            hosts = hosts.get('childEntity')
            if not hosts:
                continue

            host_obj = self._get_host_obj(host_ip)
            cluster_obj = self._get_cluster_obj(host_obj.value)
            for child in hosts[0]:
                if child._type == 'ClusterComputeResource' or\
                        child._type == 'ComputeResource':
                    if child.value == cluster_obj.value:
                        return datacenter.obj
                elif child._type == 'HostSystem':
                    if child.value == host_obj.value:
                        return datacenter.obj
                else:
                    continue
        raise vexc.ManagedObjectNotFoundException()

    def _get_cluster_obj(self, host_obj_value):
        """Get cluster reference via specified host_value from vSphere."""
        clusters = self._managed_object_get('ComputeResource')

        for cluster in clusters.objects:
            hosts = self._manager_properties_dict_get(cluster.obj, 'host')
            if not hosts.get('host'):
                continue
            for host in hosts.get('host')[0]:
                if host.value == host_obj_value:
                    return cluster.obj
        raise vexc.ManagedObjectNotFoundException()

    def _get_host_obj(self, host_ip):
        """Get host reference via specified host ipaddr from vSphere.

            e.g. (obj){
                     value = "host-140"
                     _type = "Host"
                 }
        """
        hosts = self._managed_object_get('HostSystem')
        # self._managed_object_get('HostSystem', action='cancel_retrieval')

        if host_ip == self.vsphere_ipaddr:
            # The host belong to esxi host.
            return hosts.objects[0].obj

        # The host belong to vCenter.
        for host in hosts.objects:
            if host_ip == host.propSet[0].val:
                return host.obj
        raise vexc.ManagedObjectNotFoundException()

    def _get_vm_obj(self, vm_name):
        """Get virtual machine reference via specified name from vSphere.

            e.g. (obj){
                     value = "vm-140"
                     _type = "VirtualMachine"
                 }
        """
        vms = self._managed_object_get('VirtualMachine')
        # self._managed_object_get('VirtualMachine', action='cancel_retrieval')

        for vm in vms.objects:
            if vm_name == vm.propSet[0].val:
                return vm.obj
        raise vexc.ManagedObjectNotFoundException()

    def get_res_pool(self, cluster_obj):
        """Get resource pool reference via cluster object from vSphere."""

        # Get the root resource pool of the cluster
        resource_pool = self._manager_properties_dict_get(cluster_obj,
                                                          'resourcePool')
        return resource_pool

    def get_vmfolder(self, host_ip):
        if host_ip == self.vsphere_ipaddr:
            # The host belong to vSphere(esxi).
            datacenter = self._managed_object_get('Datacenter')
            vm_folder = self._manager_properties_dict_get(
                datacenter.objects[0].obj,
                'vmFolder')
            return vm_folder.get('vmFolder')

        # The host belong to vSphere(vCenter).
        datacenter_obj = self._get_datacenter_obj(host_ip)
        vm_folder = self._manager_properties_dict_get(
            datacenter_obj,
            'vmFolder')

        vm_folder = vm_folder.get('vmFolder')
        if not vm_folder:
            raise vexc.ManagedObjectNotFoundException()
        return vm_folder

    def get_datastore_name(self, host_ip):
        if host_ip == self.vsphere_ipaddr:
            # The host belong to vSphere(esxi).
            datastore = self._managed_object_get('Datastore')
            return datastore.objects[0].propSet[0].val

        # The host belong to vSphere(vCenter).
        datastores = self._managed_object_get('Datastore')
        host_obj = self._get_host_obj(host_ip)
        for datastore in datastores.objects:
            dc_hosts = self._manager_properties_dict_get(
                datastore.obj, 'host')
            dc_hosts = dc_hosts.get('host')
            if not dc_hosts:
                continue

            for dc_host in dc_hosts[0]:
                if host_obj.value == dc_host.key.value and \
                        datastore.propSet[0].val.split('_', 1)[0] != 'Drp':
                    free_space = self._manager_properties_dict_get(
                        datastore.obj, 'summary').freeSpace
                    if free_space:
                        return datastore.propSet[0].val
        raise

    def get_vdisk_info(self, vm_name):
        """Get virtual disk information fot vmware instance."""

        vms = self._managed_object_get('VirtualMachine')
        for vm in vms[0]:
            if vm.propSet[0].val != vm_name:
                continue
            vm_extraconf = self._manager_properties_dict_get(
                vm.obj, 'config.extraConfig')

            vdisk_driver = []
            for option in vm_extraconf['config.extraConfig'][0]:
                if not option.key.find('scsi') \
                        and option.key.find('ctkEnabled') == 8 \
                        and option.value:
                    vdisk_driver.append('scsi')
                if not option.key.find('ide') \
                        and option.key.find('ctkEnabled') == 7 \
                        and option.value:
                    vdisk_driver.append('ide')
            return vdisk_driver

    def get_host_iqn(self, host_ip):
        """Return the host iSCSI IQN."""
        host_obj = self._get_host_obj(host_ip)
        hbas = self._manager_properties_dict_get(
            host_obj,
            'config.storageDevice.hostBusAdapter')

        # Meaning there are no host bus adapters on the host
        if hbas is None:
            return

        host_hbas = hbas.HostHostBusAdapter
        if not host_hbas:
            return

        for hba in host_hbas:
            if hba.__class__.__name__ == 'HostInternetScsiHba':
                return hba.iScsiName

    def get_host_initiator(self, host_ip):
        host_obj = self._get_host_obj(host_ip)
        host_storage_device = self._manager_properties_dict_get(
            host_obj, 'config.storageDevice.hostBusAdapter')

        if host_storage_device is None or \
                host_storage_device["config.storageDevice.hostBusAdapter"].\
                HostHostBusAdapter is None:
            initiator_name = None
            initiator_protocol = None

        host_bus_adapters = host_storage_device[
            "config.storageDevice.hostBusAdapter"].HostHostBusAdapter

        hba_iscsi = []
        for hba in host_bus_adapters:
            if hba.__class__.__name__ == 'HostInternetScsiHba':
                hba_iscsi.append(hba)
        # FIXME(Fan Guiju): Use many kinds of protocols.
        if not hba_iscsi or not len(hba_iscsi):
            initiator_protocol = 'ISCSI'
            initiator_name = None
        else:
            initiator_protocol = 'ISCSI'
            initiator_name = hba_iscsi[0].iScsiName
        return (initiator_protocol, initiator_name)

    def get_host_info(self, host_obj):
        host_name = host_obj.value
        # Get esxi host summary
        host_summary = self._manager_properties_dict_get(
            host_obj, 'summary').get('summary')

        # Get the sizes of esxi hypervisor memory
        if not host_summary.quickStats or\
                not host_summary.quickStats.overallMemoryUsage:
            memory_used = None
        else:
            memory_used = host_summary.quickStats.overallMemoryUsage

        # Get the esxi hardware uuid
        host_uuid = host_summary.hardware.uuid

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

        host_info = {'display_name': host_display_name,
                     'name': host_name,
                     'ip': host_ipaddr,
                     'cores': host_summary.hardware.numCpuCores,
                     'mem_used': int(memory_used) * 1024 * 1024,
                     'mem_total': host_summary.hardware.memorySize,
                     'host_uuid': host_uuid,
                     'is_vcenter': whether_is_vcenter}
        return host_info

    def get_used_vnc_port(self):

        # FIXME(Fan Guiju): We should get used vnc port for host,
        # but not vCenter, see bug #1256944
        used_vnc_ports = set()
        vms = self._managed_object_get('VirtualMachine')

        while vms:
            for vm_obj in vms.objects:
                if not hasattr(vm_obj, 'propSet'):
                    continue
                dynamic_prop = vm_obj.propSet[0]
                option_value = dynamic_prop.val
                vnc_port = option_value.value
                used_vnc_ports.add(int(vnc_port))
            self._managed_object_get(vms,
                                     action='continue_retrieval')
        return used_vnc_ports

    def get_vnc_port(self):
        # TODO(Fan Guiju): Setup the number of port with config file
        min_port = VNC_PORT_START
        port_total = VNC_PORT_TOTAL
        used_vnc_ports = self.get_used_vnc_port()
        max_port = min_port + port_total
        for port in range(min_port, max_port + 1):
            if port not in used_vnc_ports:
                return port
        raise

    def get_vswitch(self, host_ip):
        """Get vswitch reference via host ipaddr from vSphere.

        :param host_ip: ipaddress of ESXi Host.
        :type: ``str``

        :rtype: ``suds.sudsobject.ArrayOfHostVirtualSwitch``
        """
        host_obj = self._get_host_obj(host_ip)
        vswitchs = self._manager_properties_dict_get(host_obj,
                                                     'config.network.vswitch')
        return vswitchs

    def _get_add_vswitch_port_group_spec(self, client_factory,
                                         vswitch_name,
                                         port_group_name,
                                         vlan_id):
        """Builds the virtual switch port group add spec."""
        vswitch_port_group_spec = client_factory.create(
            'ns0:HostPortGroupSpec')
        vswitch_port_group_spec.name = port_group_name
        vswitch_port_group_spec.vswitchName = vswitch_name

        # VLAN ID of 0 means that VLAN tagging is not to be done for the
        # network.
        vswitch_port_group_spec.vlanId = int(vlan_id)

        policy = client_factory.create('ns0:HostNetworkPolicy')
        nicteaming = client_factory.create('ns0:HostNicTeamingPolicy')
        nicteaming.notifySwitches = True
        policy.nicTeaming = nicteaming

        vswitch_port_group_spec.policy = policy
        return vswitch_port_group_spec

    def _get_add_vswitch_spec(self, client_factory, nic, mtu_num, ports_num):
        """Builds the standard virtual switch add spec.

           :param nic: List of Physical NIC Card. e.g. ['vmnic0', 'vmnic1']
           :param mtu_num: Number of MTU.
           :param ports_num: Number of PortGroups.
        """
        hvs_spec = client_factory.create('ns0:HostVirtualSwitchSpec')

        bridge = client_factory.create('ns0:HostVirtualSwitchBondBridge')
        bridge.nicDevice = nic
        beacon = client_factory.create('ns0:HostVirtualSwitchBeaconConfig')
        beacon.interval = 1
        bridge.beacon = beacon
        link_discovery_protocol_config = client_factory.create(
            'ns0:LinkDiscoveryProtocolConfig')
        link_discovery_protocol_config.protocol = 'cdp'
        link_discovery_protocol_config.operation = 'listen'
        bridge.linkDiscoveryProtocolConfig = link_discovery_protocol_config

        hvs_spec.bridge = bridge
        hvs_spec.mtu = mtu_num
        hvs_spec.numPorts = ports_num
        return hvs_spec

    def get_svsnetwork_vlanid(self, host_obj, port_group_name):
        # Get the vlan_id with port group.
        port_group = self._manager_properties_dict_get(
            host_obj,
            'config.network.portgroup')
        if not port_group:
            vlan_id = 'None'
        host_port_groups = port_group['config.network.portgroup'].\
            HostPortGroup
        for pg in host_port_groups:
            if pg.spec.name == port_group_name:
                vlan_id = pg.spec.vlanId
        return vlan_id

    def get_dvsnetwork_info(self, network_summary, dvpg_cfg):
        dvspg_key = network_summary['summary'].network.value

        # Get overall networks
        dvpgs = self._managed_object_get('DistributedVirtualPortgroup')
        for dvpg in dvpgs.objects:
            if dvpg_cfg['config'].key != dvspg_key:
                continue

            vdvs_config = self._manager_properties_dict_get(
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

            dvsnetwork_info = {
                'dvspg_name': dvspg_name,
                'dvspg_key': dvspg_key,
                'dvs_uuid': dvs_uuid,
                'vlan_type': vlan_type,
                'vlan_id': vlan_id}
            return dvsnetwork_info

    def create_vnc_config_spec(self, client_factory):
        """Builds the vnc config spec."""

        port = self.get_vnc_port()
        opt_enabled = client_factory.create('ns0:OptionValue')
        opt_enabled.key = "RemoteDisplay.vnc.enabled"
        opt_enabled.value = "true"
        opt_port = client_factory.create('ns0:OptionValue')
        opt_port.key = "RemoteDisplay.vnc.port"
        opt_port.value = port
        opt_keymap = client_factory.create('ns0:OptionValue')
        opt_keymap.key = "RemoteDisplay.vnc.keyMap"
        opt_keymap.value = 'en-us'
        return [opt_enabled, opt_port, opt_keymap]

    def create_vm_config_spec(self, name, host_ip, flavor, vif_infos,
                              firmware=BIOS_MODE):
        """Add spec to create virtualmachine"""
        datastore_name = self.get_datastore_name(host_ip)
        client_factory = self.session.vim.client.factory
        config_spec = client_factory.create('ns0:VirtualMachineConfigSpec')

        instance_uuid = str(uuid4())
        data_store_name = datastore_name

        config_spec.name = name
        config_spec.guestId = 'otherGuest'
        config_spec.instanceUuid = instance_uuid
        config_spec.uuid = instance_uuid
        vm_file_info = client_factory.create('ns0:VirtualMachineFileInfo')
        vm_file_info.vmPathName = "[" + data_store_name + "]"
        config_spec.files = vm_file_info

        tools_info = client_factory.create('ns0:ToolsConfigInfo')
        tools_info.afterPowerOn = True
        tools_info.afterResume = True
        tools_info.beforeGuestStandby = True
        tools_info.beforeGuestShutdown = True
        tools_info.beforeGuestReboot = True
        config_spec.tools = tools_info

        config_spec.numCPUs = int(flavor.get('cpus'))
        config_spec.numCoresPerSocket = int(flavor.get('cores'))
        config_spec.memoryMB = int(flavor.get('memory_mb'))

        devices = []
        for vif_info in vif_infos:
            vif_spec = self.create_vif_config_spec(client_factory, vif_info)
            devices.append(vif_spec)

        extra_config = []
        opt = client_factory.create('ns0:OptionValue')
        opt.key = "nvp.vm-uuid"
        opt.value = instance_uuid
        extra_config.append(opt)
        if firmware == EFI_MODE:
            firmware_opt = client_factory.create('ns0:OptionValue')
            firmware_opt.key = 'firmware'
            firmware_opt.value = firmware
            extra_config.append(firmware_opt)

        vnc_opts = self.create_vnc_config_spec(client_factory)
        extra_config += vnc_opts
        config_spec.extraConfig = extra_config

        # disk config
        isci_disk_spec = self.allocate_controller_key_and_unit_number(
            client_factory)

        devices.append(isci_disk_spec)
        config_spec.deviceChange = devices

        return config_spec, vnc_opts

    def create_iface_id_config_spec(self, client_factory,
                                    iface_id, port_index):
        opt = client_factory.create('ns0:OptionValue')
        opt.key = "nvp.iface-id.%d" % port_index
        opt.value = iface_id
        return opt

    def create_vif_config_spec(self, client_factory, vif_info):
        """Create virtual network interface spec."""
        # Builds a config spec for network adapter.
        network_spec = client_factory.create('ns0:VirtualDeviceConfigSpec')
        network_spec.operation = "add"

        # Keep compatible with other Hyper vif model parameter.
        vif_info['vif_model'] = self.convert_vif_model(vif_info['vif_model'])
        vif = 'ns0:' + vif_info['vif_model']
        net_device = client_factory.create(vif)

        mac_address = vif_info['mac_address']
        network_name = vif_info['network_name']
        portgroup = vif_info['portgroup']

        # Start to select the network type
        if portgroup['type'] == 'standard_network':
            backing = client_factory.create(
                'ns0:VirtualEthernetCardNetworkBackingInfo')
            backing.deviceName = network_name
        elif portgroup['type'] == 'distributed_network':
            backing = client_factory.create(
                'ns0:VirtualEthernetCardDistributedVirtualPortBackingInfo')
            backing.port.switchUuid = portgroup['dvs_uuid']
            backing.port.portgroupKey = portgroup['dvspg_key']

        connectable_spec = client_factory.create(
            'ns0:VirtualDeviceConnectInfo')
        connectable_spec.startConnected = True
        connectable_spec.allowGuestControl = True
        connectable_spec.connected = True

        net_device.connectable = connectable_spec
        net_device.backing = backing

        # The Server assigns a Key to the device. Here we pass
        # a -ve temporary key.
        # -ve because actual keys are +ve numbers and we don't
        # want a clash with the key that server might associate
        # with the device
        net_device.key = -47
        if mac_address:
            net_device.addressType = "manual"
            net_device.macAddress = mac_address
        net_device.wakeOnLanEnabled = True

        network_spec.device = net_device
        return network_spec

    def create_vss_port_group(self, pg_name, vswitch_name, host_ip, vlan_id=0):
        """Creates a Standard vCenter vSwitch port group on specific host.

           :param pg_name: Standard vCenter vSwitch Port Group Name.
           :param vswitch_name: Name of already exists Standard vSwitch
           :param host_ip: ESXi Host Ipaddress.
           :vlan_id: id of vlan.
        """
        session = self.session
        client_factory = session.vim.client.factory
        # Make a spec for creating
        port_group_spec = self._get_add_vswitch_port_group_spec(
            client_factory, vswitch_name, pg_name, vlan_id)
        # Get host_mor for getting network_system_mor
        host_obj = self._get_host_obj(host_ip)

        network_system = self._manager_properties_dict_get(
            host_obj, 'configManager.networkSystem')
        try:
            # Execute add port group action for vSphere.
            session.invoke_api(session.vim,
                               "AddPortGroup",
                               network_system['configManager.networkSystem'],
                               portgrp=port_group_spec)
        except vexc.AlreadyExistsException:
            # There can be a race condition when two instances try
            # adding port groups at the same time. One succeeds, then
            # the other one will get an exception. Since we are
            # concerned with the port group being created, which is done
            # by the other call, we can ignore the exception.
            raise

    def create_vss(self, host_ip, vswitch_name, nic,
                   mtu_num=1500, ports_num=120):
        """Create the Standard vSwitch.

           :param host_ip: Ipaddress of ESXi Host.
           :param vswitch_name: Name of Standard vSwitch.
           :param nic: Name of Phy-NIC Cards.
           :param mtu_num: MTU number of Standard vSwitch.
           :param ports_num: PortGroup number of Standard vSwitch.
        """
        session = self.session
        client_factory = session.vim.client.factory

        host_virtual_switch_spec = self._get_add_vswitch_spec(client_factory,
                                                              nic,
                                                              mtu_num,
                                                              ports_num)
        host_obj = self._get_host_obj(host_ip)
        network_system = self._manager_properties_dict_get(
            host_obj, 'configManager.networkSystem')
        try:
            session.invoke_api(session.vim,
                               "AddVirtualSwitch",
                               network_system['configManager.networkSystem'],
                               vswitchName=vswitch_name,
                               spec=host_virtual_switch_spec)
        except vexc.AlreadyExistsException:
            raise
        except Exception:
            raise

    def remove_vss(self, host_ip, vswitch_name):
        """Remove the Standard vSwitch.

           :param host_ip: Ipaddress of ESXi host.
           :param vswitch_name: Standard vCenter vSwitch Name.
        """
        session = self.session
        host_obj = self._get_host_obj(host_ip)
        network_system = self._manager_properties_dict_get(
            host_obj, 'configManager.networkSystem')
        try:
            session.invoke_api(session.vim,
                               "RemoveVirtualSwitch",
                               network_system['configManager.networkSystem'],
                               vswitchName=vswitch_name)
        except Exception:
            raise

    def remove_vss_port_group(self, pg_name, host_ip):
        """Remove a Standard vSwitch PortGroup on specific host.

           :param pg_name: Standard vCenter vSwitch Port Group Name.
           :param host_ip: Ipaddress of ESXi host.
        """
        session = self.session
        host_obj = self._get_host_obj(host_ip)
        network_system = self._manager_properties_dict_get(
            host_obj, 'configManager.networkSystem')
        try:
            session.invoke_api(session.vim,
                               "RemovePortGroup",
                               network_system['configManager.networkSystem'],
                               pgName=pg_name)
        except Exception:
            raise

    def vm_create(self, name, host_ip, flavor, vif_infos, firmware=BIOS_MODE):
        """Create virtual machine.

        :param name: the name of vm
        :type: ``str``

        :param host_ip: specific host ip for creating vm
        :type: ``str``

        :param flavor: the flavor of vm
        :type: ``dict`` (keys: cpus, cores, memory_mb)

        :param vif_infos: the vlan interfaces infomation
        :type: ``list``

        """
        session = self.session
        host_obj = self._get_host_obj(host_ip)
        cluster_obj = self._get_cluster_obj(host_obj.value)
        config_spec, vnc_opts = self.get_vm_create_spec(name,
                                                        host_ip,
                                                        flavor,
                                                        vif_infos,
                                                        firmware=firmware)
        vm_folder = self.get_vmfolder(host_ip)
        res_pool = self.get_res_pool(cluster_obj)

        vm_create_task = session.invoke_api(session.vim,
                                            "CreateVM_Task",
                                            vm_folder,
                                            config=config_spec,
                                            pool=res_pool,
                                            host=host_obj)

        task_info = session.wait_for_task(vm_create_task)
        return task_info.result, config_spec.instanceUuid, vnc_opts

    def vm_power_action(self, vm_name, action):
        """Virtual machine action

        :param vm_name: the name of vm
        :type: ``str``

        :param action: the operation of vm, it's value should be selected in
                       restart, power_on and power_off
        :type: ``str``

        """
        session = self.session
        vm_obj = self._get_vm_obj(vm_name)

        if action == 'restart':
            poweroff_task = session.invoke_api(session.vim,
                                               "PowerOffVM_Task", vm_obj)
            session.wait_for_task(poweroff_task)

            poweron_task = session.invoke_api(session.vim,
                                              "PowerOnVM_Task", vm_obj)
            session.wait_for_task(poweron_task)
            return

        elif action == 'power_on':
            poweron_task = session.invoke_api(session.vim,
                                              "PowerOnVM_Task", vm_obj)
            session.wait_for_task(poweron_task)
            return

        elif action == 'power_off':
            poweroff_task = session.invoke_api(session.vim,
                                               "PowerOffVM_Task", vm_obj)
            session.wait_for_task(poweroff_task)
            return

        elif action == 'destroy':
            if self.vm_state(vm_name) == "poweredOn":
                self.vm_action(vm_name, 'power_off')

            destroy_task = session.invoke_api(session.vim,
                                              "Destroy_Task", vm_obj)
            session.wait_for_task(destroy_task)
            return

        else:
            raise Exception("Virtual machine method %s not found!" % action)

    def vm_live_migration(self, vm_name, desc_host_ip):
        """Virtual Machine vMotion migration.

           vCenter Configuration Condition 1: Shared storage between different
                                              hosts(iSCSI Shared Storage)
           vCenter Configuration Condition 2: Network interconnection between
                                              different hosts(VM Network)
           :param vm_name: Name of vCenter virtualmachine.
           :param host_ip: Ipaddress of DEST Migration ESXi Host.
        """
        session = self.session

        host_obj = self._get_host_obj(desc_host_ip)
        vm_obj = self._get_vm_obj(vm_name)
        vms_obj = self._get_vm_via_host_obj(host_obj)

        if not vms_obj:
            raise
        if vm_obj in vms_obj:
            raise

        try:
            migration_task = session.invoke_api(
                session.vim,
                'MigrateVM_Task',
                vm_obj,
                host=host_obj,
                priority='defaultPriority')
        except Exception:
            raise

        result = self._wait_for_task(migration_task)
        return result

    def _get_vm_via_host_obj(self, host_obj):
        vms = self._manager_properties_dict_get(host_obj, 'vm')
        if vms:
            return vms['vm']
        return None

    def vm_state(self, vm_name):
        """Get vm state"""
        vm_obj = self._get_vm_obj(vm_name)
        vm_info = self._manager_properties_dict_get(vm_obj, 'summary')
        vm_summary = vm_info.get('summary')

        if not vm_summary:
            return
        return vm_summary.runtime.powerState

    def vm_reconfig(self, vm_name, host_ip, flavor, vif_infos, set_vnc=True):
        """Reconfigure a VM according to the config spec."""
        session = self.session
        vm_obj = self._get_vm_obj(vm_name)
        config_spec, vnc_opts = self.change_vm_config(vm_name,
                                                      flavor,
                                                      vif_infos,
                                                      set_vnc=set_vnc)
        reconfig_task = session.invoke_api(session.vim,
                                           "ReconfigVM_Task",
                                           vm_obj,
                                           spec=config_spec)
        session.wait_for_task(reconfig_task)
        return vnc_opts

    def convert_vif_model(self, name):
        # Converts standard VIF_MODEL types to the internal VMware ones.
        if name == VIF_MODEL_E1000:
            return 'VirtualE1000'
        if name == VIF_MODEL_E1000E:
            return 'VirtualE1000e'
        if name == VIF_MODEL_PCNET:
            return 'VirtualPCNet32'
        if name == VIF_MODEL_SRIOV:
            return 'VirtualSriovEthernetCard'
        if name == VIF_MODEL_VMXNET:
            return 'VirtualVmxnet'
        if name == VIF_MODEL_VMXNET3:
            return 'VirtualVmxnet3'
        else:
            raise
        return name

    def change_vm_config(self, name, flavor, vif_infos, set_vnc=True):
        client_factory = self.session.vim.client.factory
        config_spec = client_factory.create('ns0:VirtualMachineConfigSpec')

        config_spec.name = name

        config_spec.numCPUs = int(flavor.get('cpus'))
        config_spec.numCoresPerSocket = int(flavor.get('cores'))
        config_spec.memoryMB = int(flavor.get('memory_mb'))

        devices = []
        count = 0
        extra_config = []
        for vif_info in vif_infos:
            vif_info['iface_id'] = count
            vif_spec = self.create_vif_config_spec(client_factory, vif_info)
            devices.append(vif_spec)
            extra_config.append(self.create_iface_id_config_spec(
                client_factory,
                vif_info['iface_id'],
                count))
            count += 1
        config_spec.deviceChange = devices

        if set_vnc:
            vnc_opts = self.create_vnc_config_spec(client_factory)
            extra_config += vnc_opts
        else:
            vnc_opts = None
        config_spec.extraConfig = extra_config

        return config_spec, vnc_opts

    def ensure_network_obj_is_uplink(self, network_obj, is_vcenter):
        network_summary = self._manager_properties_dict_get(
            network_obj, 'summary')
        if network_summary['summary'].\
                network._type == 'DistributedVirtualPortgroup' \
                and is_vcenter:
            dvpg_cfg = self._manager_properties_dict_get(
                network_obj,
                'config')
            # Virtual machine can't be use the uplink_portgroup
            if dvpg_cfg['config'].defaultPortConfig.\
                    uplinkTeamingPolicy.uplinkPortOrder.inherited:
                return True
            return False

    def allocate_controller_key_and_unit_number(self,
                                                client_factory,
                                                adapter_type='lsiLogic'):
        """This function inspects the current set of hardware devices and

        returns controller_key and unit_number that can be used for attaching

        a new virtual disk to adapter with the given adapter_type.
        """

        def create_controller_spec(client_factory,
                                   key,
                                   adapter_type='lsiLogic',
                                   bus_number=0):
            """Builds a Config Spec for the LSI or Bus Logic Controller's

            addition which acts as the controller for the virtual hard disk

            to be attached to the VM.
            """
            # Create a controller for the Virtual Hard Disk
            virtual_device_config = client_factory.create(
                'ns0:VirtualDeviceConfigSpec')
            virtual_device_config.operation = "add"
            if adapter_type == "busLogic":
                virtual_controller = client_factory.create(
                    'ns0:VirtualBusLogicController')
            elif adapter_type == "lsiLogicsas":
                virtual_controller = client_factory.create(
                    'ns0:VirtualLsiLogicSASController')
            elif adapter_type == "paraVirtual":
                virtual_controller = client_factory.create(
                    'ns0:ParaVirtualSCSIController')
            else:
                virtual_controller = client_factory.create(
                    'ns0:VirtualLsiLogicController')
            virtual_controller.key = key
            virtual_controller.busNumber = bus_number
            virtual_controller.sharedBus = "noSharing"
            virtual_device_config.device = virtual_controller
            return virtual_device_config

        # create new controller with the specified type and return its spec
        controller_key = -101

        # Get free bus number for new SCSI controller.
        bus_number = 0

        controller_spec = create_controller_spec(
            client_factory, controller_key,
            adapter_type, bus_number)
        return controller_spec
