# Copyright 2016 Beijing Huron Technology Co.Ltd.
#
# Authors: He Qun <hequn@hihuron.com>
# Authors: Fan Guiju <fanguiju@hihuron.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""VMWare client"""

from urlparse import urlparse
import uuid

from oslo_config import cfg
from oslo_log import log as logging
from oslo_vmware import exceptions as vexc
from oslo_vmware import vim_util

from egis import exception
from egis.i18n import _, _LE, _LI
from egis.virt.vmware import session as vmware_session
from egis.virt.vmware import vif_model as network_model
from egis.virt.vmware import vim_util as vutil


VMWARE_OPTS = [
    cfg.IntOpt('vnc_port_start', default=5900,
               help='Start port of vnc.'),
    cfg.IntOpt('vnc_port_total', default=1000,
               help='End port of vnc.')
]

CONF = cfg.CONF
CONF.register_opts(VMWARE_OPTS, 'vmware')

LOG = logging.getLogger(__name__)
VNC_CONFIG_KEY = 'config.extraConfig["RemoteDisplay.vnc.port"]'

API_RETRY_COUNT = 2
TASK_POLL_INTERVAL = 3
MAX_SINGLE_CALL = 100
BIOS_MODE = 'bios'
EFI_MODE = 'efi'


class VmwareClient(object):

    def __init__(self, auth_url, username, password):
        self.vcenter_ip = urlparse(auth_url).hostname
        self.session = vmware_session.get_session(
            auth_url,
            username,
            password)

    def get_host_initiator(self, host_ip):
        session = self.session
        host = self._get_host_ref(host_ip)
        host_storage_device = session.invoke_api(
            vim_util, 'get_object_properties_dict',
            session.vim, host,
            'config.storageDevice.hostBusAdapter')

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

    def _get_host_ref(self, host_ip):
        """Get reference to a host within the host specified.

        :param host_ip: the ip of host
        :type: ``str``

        :rtype: (obj){
                    value = "host-140"
                    _type = "Host"
                }

        """
        session = self.session
        # param: maximum number of objects that should be returned in a
        #        single call = 100
        results = session.invoke_api(vim_util, "get_objects",
                                     session.vim, "HostSystem",
                                     MAX_SINGLE_CALL)

        session.invoke_api(vim_util, 'cancel_retrieval', session.vim, results)

        # is esxi host
        if host_ip == self.vcenter_ip:
            return results.objects[0].obj

        # is vcenter
        for host in results.objects:
            if host_ip == host.propSet[0].val:
                return host.obj

        LOG.error(_LE("Host: %s not found!") % host_ip)
        raise vexc.ManagedObjectNotFoundException()

    def _get_vm_ref(self, vm_name):
        """Get reference to a vm within the vm name specified.

        :param vm_name: the name of vm
        :type: ``str``

        :rtype: (obj){
                    value = "vm-140"
                    _type = "VirtualMachine"
                }
        """
        session = self.session
        results = session.invoke_api(vim_util, "get_objects",
                                     session.vim, "VirtualMachine",
                                     MAX_SINGLE_CALL)

        session.invoke_api(vim_util, 'cancel_retrieval', session.vim, results)

        for vm in results.objects:
            if vm_name == vm.propSet[0].val:
                return vm.obj

        LOG.error(_LE("Virtualmachine: %s not found!") % vm_name)
        raise vexc.ManagedObjectNotFoundException()

    def get_vdisk_info(self, vm_name):
        """Get virtual disk information fot vmware instance."""

        session = self.session
        vms = session.invoke_api(vim_util, 'get_objects',
                                 session.vim, 'VirtualMachine',
                                 MAX_SINGLE_CALL)
        for vm in vms[0]:
            if vm.propSet[0].val != vm_name:
                continue
            vm_extraconf = session.invoke_api(
                vim_util, 'get_object_properties_dict',
                session.vim, vm.obj, 'config.extraConfig')

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

    def _get_cluster_ref(self, host_value):
        session = self.session
        clusters = session.invoke_api(vim_util, "get_objects",
                                      session.vim, "ComputeResource",
                                      MAX_SINGLE_CALL)
        for cluster in clusters.objects:
            hosts = session.invoke_api(vim_util, 'get_object_properties_dict',
                                       session.vim, cluster.obj, 'host')
            if not hosts.get('host'):
                continue

            for host in hosts.get('host')[0]:
                if host.value == host_value:
                    return cluster.obj

        LOG.error(_LE("Cluster not found in host: %s") % host_value)
        raise vexc.ManagedObjectNotFoundException()

    def get_vswitch(self, host_ip):
        """Get vswitch name.

        :param host_ip: the host of ip
        :type: ``str``

        :rtype: ``suds.sudsobject.ArrayOfHostVirtualSwitch``
        """
        session = self.session
        host_mor = self._get_host_ref(host_ip)
        vswitches_ret = session.invoke_api(vim_util, "get_object_property",
                                           session.vim, host_mor,
                                           "config.network.vswitch")
        return vswitches_ret

    def _get_add_vswitch_port_group_spec(self, client_factory, vswitch_name,
                                         port_group_name, vlan_id):
        # Add spec to the virtual switch port.
        vswitch_port_group_spec = client_factory.\
            create('ns0:HostPortGroupSpec')
        vswitch_port_group_spec.name = port_group_name
        vswitch_port_group_spec.vswitchName = vswitch_name
        # VLAN ID of 0 means that VLAN tagging is not to be
        # done for the network.
        vswitch_port_group_spec.vlanId = int(vlan_id)

        policy = client_factory.create('ns0:HostNetworkPolicy')
        nicteaming = client_factory.create('ns0:HostNicTeamingPolicy')
        nicteaming.notifySwitches = True
        policy.nicTeaming = nicteaming

        vswitch_port_group_spec.policy = policy
        return vswitch_port_group_spec

    def _convert_vif_model(self, name):
        # Converts standard VIF_MODEL types to the internal VMware ones.
        if name == network_model.VIF_MODEL_E1000:
            return 'VirtualE1000'
        if name == network_model.VIF_MODEL_E1000E:
            return 'VirtualE1000e'
        if name == network_model.VIF_MODEL_PCNET:
            return 'VirtualPCNet32'
        if name == network_model.VIF_MODEL_SRIOV:
            return 'VirtualSriovEthernetCard'
        if name == network_model.VIF_MODEL_VMXNET:
            return 'VirtualVmxnet'
        if name == network_model.VIF_MODEL_VMXNET3:
            return 'VirtualVmxnet3'
        else:
            msg = _('%s is not supported.') % name
            raise exception.Invalid(msg)
        return name

    def _create_vif_spec(self, client_factory, vif_info):
        # Builds a config spec for network adapter.
        network_spec = client_factory.create('ns0:VirtualDeviceConfigSpec')
        network_spec.operation = "add"

        # Keep compatible with other Hyper vif model parameter.
        vif_info['vif_model'] = self._convert_vif_model(vif_info['vif_model'])
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

    def _iface_id_option(self, client_factory, iface_id, port_index):
        opt = client_factory.create('ns0:OptionValue')
        opt.key = "nvp.iface-id.%d" % port_index
        opt.value = iface_id
        return opt

    def _config_change(self, name, flavor, vif_infos, set_vnc=True):
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
            vif_spec = self._create_vif_spec(client_factory, vif_info)
            devices.append(vif_spec)
            extra_config.append(self._iface_id_option(client_factory,
                                                      vif_info['iface_id'],
                                                      count))
            count += 1
        config_spec.deviceChange = devices

        if set_vnc:
            vnc_opts = self._get_vnc_config_spec(client_factory)
            extra_config += vnc_opts
        else:
            vnc_opts = None
        config_spec.extraConfig = extra_config

        return config_spec, vnc_opts

    def _get_vm_create_spec(self, name, host_ip, flavor, vif_infos,
                            firmware=BIOS_MODE):
        """Add spec to create virtualmachine"""
        datastore_name = self.get_datastore_name(host_ip)
        client_factory = self.session.vim.client.factory
        config_spec = client_factory.create('ns0:VirtualMachineConfigSpec')

        instance_uuid = str(uuid.uuid4())
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
            vif_spec = self._create_vif_spec(client_factory, vif_info)
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

        vnc_opts = self._get_vnc_config_spec(client_factory)
        extra_config += vnc_opts
        config_spec.extraConfig = extra_config

        # disk config
        isci_disk_spec = self.allocate_controller_key_and_unit_number(
            client_factory)

        devices.append(isci_disk_spec)
        config_spec.deviceChange = devices

        return config_spec, vnc_opts

    def _get_res_pool_ref(self, cluster):
        """Get the resource pool."""
        # Get the root resource pool of the cluster
        session = self.session
        res_pool_ref = session.invoke_api(vim_util,
                                          "get_object_property",
                                          session.vim,
                                          cluster,
                                          "resourcePool")
        return res_pool_ref

    def get_datacenter_by_host(self, host_ip):
        session = self.session
        datacenters = session.invoke_api(vim_util, 'get_objects', session.vim,
                                         'Datacenter', MAX_SINGLE_CALL)
        for datacenter in datacenters.objects:
            res_folder = session.invoke_api(vim_util,
                                            'get_object_properties_dict',
                                            session.vim,
                                            datacenter.obj, 'hostFolder')

            host_folder = res_folder.get('hostFolder')

            if not host_folder:
                continue

            hosts = session.invoke_api(vim_util,
                                       'get_object_properties_dict',
                                       session.vim,
                                       host_folder, 'childEntity')

            hosts = hosts.get('childEntity')

            if not hosts:
                continue

            # NOTE(He Qun): because of host folder have cluster and host
            #               infomation, we need to match host use difference
            #               method.
            host = self._get_host_ref(host_ip)
            specific_cluster = self._get_cluster_ref(host.value)
            for child in hosts[0]:
                if child._type == 'ClusterComputeResource' or\
                        child._type == 'ComputeResource':
                    if child.value == specific_cluster.value:
                        return datacenter.obj

                elif child._type == 'HostSystem':
                    if child.value == host.value:
                        return datacenter.obj

                else:
                    continue

        LOG.error(_LE("Datacenter not found in host: %s!") % host_ip)
        raise vexc.ManagedObjectNotFoundException()

    def _get_vmfolder_ref(self, host_ip):
        session = self.session
        # ESXi host
        if host_ip == self.vcenter_ip:
            datacenter = session.invoke_api(vim_util, 'get_objects',
                                            session.vim,
                                            'Datacenter', MAX_SINGLE_CALL)
            vmFolder = session.invoke_api(vim_util,
                                          'get_object_properties_dict',
                                          session.vim,
                                          datacenter.objects[0].obj,
                                          'vmFolder')
            return vmFolder.get('vmFolder')

        # Vcenter
        # NOTE(He Qun): we find vmfolder by specified host, because of
        #               datacenter have not host infomation, so we get
        #               cluster infomation to match host and datacenter.
        datacenter = self.get_datacenter_by_host(host_ip)
        vmFolder = session.invoke_api(vim_util, 'get_object_properties_dict',
                                      session.vim, datacenter, 'vmFolder')

        vmfolder = vmFolder.get('vmFolder')
        if not vmfolder:
            LOG.error(_LE("Vmfolder not found in host: %s!") % host_ip)
            raise vexc.ManagedObjectNotFoundException()
        return vmfolder

    def get_datastore_name(self, host_ip):
        session = self.session
        # ESXi host
        if host_ip == self.vcenter_ip:
            datastore = session.invoke_api(vim_util, 'get_objects',
                                           session.vim, 'Datastore',
                                           MAX_SINGLE_CALL)
            return datastore.objects[0].propSet[0].val

        # Vcenter
        datastores = session.invoke_api(vim_util, 'get_objects', session.vim,
                                        'Datastore', MAX_SINGLE_CALL)
        host = self._get_host_ref(host_ip)
        for datastore in datastores.objects:
            dc_hosts = session.invoke_api(vim_util,
                                          'get_object_properties_dict',
                                          session.vim,
                                          datastore.obj, 'host')
            dc_hosts = dc_hosts.get('host')

            if not dc_hosts:
                continue

            for dc_host in dc_hosts[0]:
                if host.value == dc_host.key.value and \
                        datastore.propSet[0].val.split('_', 1)[0] != 'Drp':
                    free_space = session.invoke_api(vim_util,
                                                    "get_object_property",
                                                    session.vim,
                                                    datastore.obj,
                                                    "summary").freeSpace
                    if free_space:
                        return datastore.propSet[0].val

        LOG.error(_LE("Datastore not found in host: %s!") % host_ip)
        raise exception.NoDataStore(host=host_ip)

    def create_port_group(self, pg_name, vswitch_name, host_ip, vlan_id=0):
        """Creates a port group on specific host."""
        session = self.session
        client_factory = session.vim.client.factory
        # Make a spec for creating
        add_prt_grp_spec = self._get_add_vswitch_port_group_spec(
            client_factory, vswitch_name, pg_name, vlan_id)
        # Get host_mor for getting network_system_mor
        host_mor = self._get_host_ref(host_ip)

        network_system_mor = session.invoke_api(vim_util,
                                                "get_object_property",
                                                session.vim,
                                                host_mor,
                                                "configManager.networkSystem")
        LOG.info(_LI("Creating Port Group with name %(pg)s on the ESXi "
                     "host: %(host)s"), {'pg': pg_name, 'host': host_ip})
        try:
            session.invoke_api(session.vim,
                               "AddPortGroup", network_system_mor,
                               portgrp=add_prt_grp_spec)
        except vexc.AlreadyExistsException:
            # There can be a race condition when two instances try
            # adding port groups at the same time. One succeeds, then
            # the other one will get an exception. Since we are
            # concerned with the port group being created, which is done
            # by the other call, we can ignore the exception.
            LOG.error(_LE("Port Group %(pg)s already exist in host: "
                          "%(host)s."), {'pg': pg_name, 'host': host_ip})
        LOG.info(_LI("Created Port Group with name %(pg)s on the ESXi "
                     "host: %(host)s"), {'pg': pg_name, 'host': host_ip})

    def remove_port_group(self, pg_name, host_ip):
        """Remove a port group on the host system"""
        # FIXME(hequn): we need to know the type of pg_name, send string type
        #               to oslo_vmware will cause error.
        session = self.session
        host_mor = self._get_host_ref(host_ip)
        network_system_mor = session.invoke_api(vim_util,
                                                "get_object_property",
                                                session.vim,
                                                host_mor,
                                                "configManager.networkSystem")

        session.invoke_api(session.vim, "RemovePortGroup",
                           network_system_mor, pg_name)

    def vm_action(self, vm_name, action):
        """Virtual machine action

        :param vm_name: the name of vm
        :type: ``str``

        :param action: the operation of vm, it's value should be selected in
                       restart, power_on and power_off
        :type: ``str``

        """
        session = self.session
        vm_ref = self._get_vm_ref(vm_name)
        if action == 'restart':
            poweroff_task = session.invoke_api(session.vim,
                                               "PowerOffVM_Task", vm_ref)
            session.wait_for_task(poweroff_task)
            poweron_task = session.invoke_api(session.vim,
                                              "PowerOnVM_Task", vm_ref)
            session.wait_for_task(poweron_task)
            return

        elif action == 'power_on':
            poweron_task = session.invoke_api(session.vim,
                                              "PowerOnVM_Task", vm_ref)
            session.wait_for_task(poweron_task)
            return

        elif action == 'power_off':
            poweroff_task = session.invoke_api(session.vim,
                                               "PowerOffVM_Task", vm_ref)
            session.wait_for_task(poweroff_task)
            return

        elif action == 'destroy':
            if self.vm_state(vm_name) == "poweredOn":
                self.vm_action(vm_name, 'power_off')

            destroy_task = session.invoke_api(session.vim,
                                              "Destroy_Task", vm_ref)
            session.wait_for_task(destroy_task)
            return

        else:
            raise Exception("Virtual machine method %s not found!" % action)

    def vm_create(self, name, host_ip, flavor, vif_infos, firmware=BIOS_MODE):
        """Virtual machine create

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
        host_ref = self._get_host_ref(host_ip)
        cluster = self._get_cluster_ref(host_ref.value)
        config_spec, vnc_opts = self._get_vm_create_spec(name,
                                                         host_ip,
                                                         flavor,
                                                         vif_infos,
                                                         firmware=firmware)
        vmfolder = self._get_vmfolder_ref(host_ip)
        res_pool_ref = self._get_res_pool_ref(cluster)

        vm_create_task = session.invoke_api(session.vim,
                                            "CreateVM_Task",
                                            vmfolder,
                                            config=config_spec,
                                            pool=res_pool_ref,
                                            host=host_ref)

        task_info = session.wait_for_task(vm_create_task)
        LOG.info(_LI("Created VM on the ESX host: %s") % host_ip)
        return task_info.result, config_spec.instanceUuid, vnc_opts

    def get_host_iqn(self, host_ip):
        """Return the host iSCSI IQN."""
        host_mor = self._get_host_ref(host_ip)
        hbas_ret = self.session.invoke_api(vim_util,
                                           "get_object_property",
                                           self.session.vim,
                                           host_mor,
                                           "config.storageDevice."
                                           "hostBusAdapter")

        # Meaning there are no host bus adapters on the host
        if hbas_ret is None:
            return
        host_hbas = hbas_ret.HostHostBusAdapter
        if not host_hbas:
            return
        for hba in host_hbas:
            if hba.__class__.__name__ == 'HostInternetScsiHba':
                return hba.iScsiName

    def vm_state(self, vm_name):
        """Get vm state"""
        session = self.session
        vm_ref = self._get_vm_ref(vm_name)
        vm_info = session.invoke_api(vim_util, 'get_object_properties_dict',
                                     session.vim, vm_ref, 'summary')
        vm_summary = vm_info.get('summary')

        if not vm_summary:
            return

        return vm_summary.runtime.powerState

    def vm_config(self, vm_name, host_ip, flavor, vif_infos, set_vnc=True):
        """Reconfigure a VM according to the config spec."""
        session = self.session
        vm_ref = self._get_vm_ref(vm_name)
        config_spec, vnc_opts = self._config_change(vm_name,
                                                    flavor,
                                                    vif_infos,
                                                    set_vnc=set_vnc)
        reconfig_task = session.invoke_api(session.vim,
                                           "ReconfigVM_Task", vm_ref,
                                           spec=config_spec)
        session.wait_for_task(reconfig_task)
        LOG.info(_LI("Config VM on the ESX host: %s") % host_ip)
        return vm_ref, vnc_opts

    def allocate_controller_key_and_unit_number(self, client_factory,
                                                adapter_type='lsiLogic'):
        """This function inspects the current set of hardware devices and

        returns controller_key and unit_number that can be used for attaching

        a new virtual disk to adapter with the given adapter_type.
        """

        def create_controller_spec(client_factory, key,
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

    def _get_used_vnc_port(self):
        # FIXME(Li Xiepng): We should get used vnc port for host,
        # but not vCenter, see bug #1256944
        used_vnc_ports = set()
        session = self.session
        vms = session.invoke_api(vutil, 'get_objects', session.vim,
                                 'VirtualMachine', [VNC_CONFIG_KEY])
        while vms:
            for obj in vms.objects:
                if not hasattr(obj, 'propSet'):
                    continue
                dynamic_prop = obj.propSet[0]
                option_value = dynamic_prop.val
                vnc_port = option_value.value
                used_vnc_ports.add(int(vnc_port))
            vms = session.invoke_api(vim_util,
                                     'continue_retrieval',
                                     session.vim,
                                     vms)
        return used_vnc_ports

    def _get_vnc_port(self):
        # TODO(Fan Guiju): Setup the number of port with config file
        min_port = CONF.vmware.vnc_port_start
        port_total = CONF.vmware.vnc_port_total
        used_vnc_ports = self._get_used_vnc_port()
        max_port = min_port + port_total
        for port in range(min_port, max_port):
            if port not in used_vnc_ports:
                return port

        exception.ConsolePortRangeExhausted(min_port=min_port,
                                            max_port=max_port)

    def _get_vnc_config_spec(self, client_factory):
        """Builds the vnc config spec."""
        port = self._get_vnc_port()
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
