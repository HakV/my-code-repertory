# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Piston Cloud Computing, Inc.
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
"""
SQLAlchemy models for octopunch data.
"""

from oslo_config import cfg
from oslo_db.sqlalchemy import models
from sqlalchemy import Boolean, Column, ForeignKey, Integer
from sqlalchemy import String, Table, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


CONF = cfg.CONF
BASE = declarative_base()


hosts_datastores = Table(
    'hosts_datastores', BASE.metadata,
    Column('host_uuid', String(length=45), ForeignKey('hosts.uuid')),
    Column('datastore_uuid', String(length=45),
           ForeignKey('datastores.uuid')),
    mysql_engine='InnoDB'
)

virtual_machines_datastores = Table(
    'virtual_machines_datastores', BASE.metadata,
    Column('virtual_machine_uuid', String(length=45),
           ForeignKey('virtual_machines.uuid')),
    Column('datastore_uuid', String(length=45),
           ForeignKey('datastores.uuid')),
    mysql_engine='InnoDB'
)

virtual_machines_networks = Table(
    'virtual_machines_networks', BASE.metadata,
    Column('virtual_machine_uuid', String(length=45),
           ForeignKey('virtual_machines.uuid')),
    Column('network_uuid', String(length=45),
           ForeignKey('networks.uuid')),
    mysql_engine='InnoDB'
)

hosts_networks = Table(
    'hosts_networks', BASE.metadata,
    Column('host_uuid', String(length=45), ForeignKey('hosts.uuid')),
    Column('network_uuid', String(length=45),
           ForeignKey('networks.uuid')),
    mysql_engine='InnoDB'
)


class OctopunchBase(models.TimestampMixin, models.ModelBase):
    """Base class for Octopunch Models."""

    __table_args__ = {'mysql_engine': 'InnoDB'}

    # TODO(rpodolyaka): reuse models.SoftDeleteMixin in the next stage
    #                   of implementing of BP db-cleanup
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    deleted_at = Column(DateTime)
    uuid = Column(String(45), primary_key=True)
    metadata = None


class Vcenter(BASE, OctopunchBase):
    """Represents the vcenter list."""

    __tablename__ = 'vcenters'
    vc_value = Column(String(255))
    name = Column(String(255))
    vcs_ip = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    password = Column(String(255), nullable=False)

    datacenters = relationship('Datacenter', backref='vcenters',
                               foreign_keys='Datacenter.vcenter_uuid',
                               primaryjoin='Vcenter.uuid =='
                                           'Datacenter.vcenter_uuid')


class Datacenter(BASE, OctopunchBase):
    """Represents the datacenter list."""

    __tablename__ = 'datacenters'
    dc_value = Column(String(255))
    name = Column(String(255))
    vcenter_uuid = Column(String(45), ForeignKey('vcenters.uuid'),
                          nullable=False)

    clusters = relationship('Cluster', backref='datacenters',
                            foreign_keys='Cluster.datacenter_uuid',
                            primaryjoin='Datacenter.uuid =='
                                        'Cluster.datacenter_uuid')


class Cluster(BASE, OctopunchBase):
    """Represents the cluster list."""

    __tablename__ = 'clusters'
    cls_value = Column(String(255))
    name = Column(String(255))
    overall_cpu_count = Column(Integer)
    overall_cpu_mhz = Column(Integer)
    overall_mem_sizemb = Column(Integer)
    overall_storage_sizemb = Column(Integer)
    datacenter_uuid = Column(String(45), ForeignKey('datacenters.uuid'),
                             nullable=False)

    resource_pools = relationship('ResourcePool', backref='clusters',
                                  foreign_keys='ResourcePool.cluster_uuid',
                                  primaryjoin='Cluster.uuid =='
                                              'ResourcePool.cluster_uuid')

    hosts = relationship('Host', backref='clusters',
                         foreign_keys='Host.cluster_uuid',
                         primaryjoin='Cluster.uuid =='
                                     'Host.cluster_uuid')


class ResourcePool(BASE, OctopunchBase):
    """Represents the resource pool list."""

    __tablename__ = 'resource_pools'
    res_value = Column(String(255))
    name = Column(String(255))
    res_type = Column(String(255))
    res_overall_cpu_count = Column(Integer)
    res_overall_cpu_mhz = Column(Integer)
    res_overhead_cpu_mmhz = Column(Integer)
    res_overall_mem_sizemb = Column(Integer)
    res_overhead_mem_sizemb = Column(Integer)
    cluster_uuid = Column(String(45), ForeignKey('clusters.uuid'),
                          nullable=False)

    hosts = relationship('Host', backref='resource_pools',
                         foreign_keys='Host.resource_pool_uuid',
                         primaryjoin='ResourcePool.uuid =='
                                     'Host.resource_pool_uuid')


class Host(BASE, OctopunchBase):
    """Represents the host list."""

    __tablename__ = 'hosts'
    host_value = Column(String(45))
    name = Column(String(45))
    host_ip = Column(String(45), nullable=False)
    hardware_cpu_count = Column(Integer)
    hardware_cpu_mhz = Column(Integer)
    overhead_cpu_mhz = Column(Integer)
    hardware_mem_sizemb = Column(Integer)
    overhead_mem_sizemb = Column(Integer)
    hardware_nic_count = Column(Integer)
    state_power = Column(String(255))
    state_connect = Column(Boolean)
    cluster_uuid = Column(String(45), ForeignKey('hosts.uuid'))
    resource_pool_uuid = Column(String(45),
                                ForeignKey('resource_pools.uuid'))

    vstd_switchs = relationship('VstdSwitchs', backref='hosts',
                                foreign_keys='VstdSwitchs.host_uuid',
                                primaryjoin='Host.uuid =='
                                            'VstdSwitchs.host_uuid')

    virtual_machines = relationship('VirtualMachine', backref='hosts',
                                    foreign_keys='VirtualMachine.host_uuid',
                                    primaryjoin='Host.uuid =='
                                                'VirtualMachine.host_uuid')

    datastores = relationship('Datastore', secondary='hosts_datastores',
                              back_populates='hosts')

    networks = relationship('Network', secondary='hosts_networks',
                            back_populates='hosts')


class VirtualMachine(BASE, OctopunchBase):
    """Represents the virtual machine list."""

    __tablename__ = 'virtual_machines'
    vm_value = Column(String(255))
    name = Column(String(255))
    guest_os = Column(String(255))
    vdisk_count = Column(Integer)
    vdisk_sizemb = Column(Integer)
    vcpu_count = Column(Integer)
    vcpu_mhz = Column(Integer)
    vcpu_overhead_mhz = Column(Integer)
    mem_sizemb = Column(Integer)
    mem_overhead_sizemb = Column(Integer)
    statr_vm_power = Column(String(255))
    guest_nic_count = Column(Integer)
    project_id = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False)
    host_uuid = Column(String(45), ForeignKey('hosts.uuid'),
                       nullable=False)

    guest_nics = relationship('GuestNics', backref='virtual_machines',
                              foreign_keys='GuestNics.virtual_machine_uuid',
                              primaryjoin='VirtualMachine.uuid =='
                                          'GuestNics.virtual_machine_uuid')

    datastores = relationship('Datastore',
                              secondary='virtual_machines_datastores',
                              back_populates='virtual_machines')

    networks = relationship('Network',
                            secondary='virtual_machines_networks',
                            back_populates='virtual_machines')


class Datastore(BASE, OctopunchBase):
    """Represents the datastore list."""

    __tablename__ = 'datastores'
    ds_value = Column(String(45))
    name = Column(String(255))
    ds_type = Column(String(255))
    url = Column(String(255))
    access_mode = Column(String(255))
    accssible = Column(Boolean)
    state_mount = Column(Boolean)
    capacity_sizemb = Column(Integer)
    free_space_sizemb = Column(Integer)

    hosts = relationship('Host', secondary='hosts_datastores',
                         back_populates='datastores')

    virtual_machines = relationship('VirtualMachine',
                                    secondary='virtual_machines_datastores',
                                    back_populates='datastores')


class VstdSwitchs(BASE, OctopunchBase):
    """Represents the virtual standard switch list."""

    __tablename__ = 'vstd_switchs'
    vsh_value = Column(String(255))
    name = Column(String(255))
    port_count = Column(Integer)
    mtu_count = Column(Integer)
    phy_adapter_name = Column(String(255))
    host_uuid = Column(String(45), ForeignKey('hosts.uuid'),
                       nullable=False)


class Network(BASE, OctopunchBase):
    """Represents the network list."""

    __tablename__ = 'networks'
    net_value = Column(String(255))
    name = Column(String(255))
    ip_pool = Column(String(255))

    virtual_machines = relationship('VirtualMachine',
                                    secondary='virtual_machines_networks',
                                    back_populates='networks')

    hosts = relationship('Host', secondary='hosts_networks',
                         back_populates='networks')


class GuestNics(BASE, OctopunchBase):
    """Represents the nic list of virtual machine."""

    __tablename__ = 'guest_nics'
    gn_value = Column(String(255))
    ip_address = Column(String(255))
    mac_address = Column(String(255))
    virtual_machine_uuid = Column(String(45),
                                  ForeignKey('virtual_machines.uuid'),
                                  nullable=False)


def register_models():
    """Register Models and create metadata.

    Called from octopunch.db.sqlalchemy.__init__ as part of loading the driver,
    it will never need to be called explicitly elsewhere unless the
    connection is lost and needs to be reestablished.
    """
    from sqlalchemy import create_engine
    models = (Vcenter,
              Datacenter,
              Cluster,
              ResourcePool,
              Host,
              VirtualMachine,
              Datastore,
              Network,
              VstdSwitchs,
              GuestNics)
    engine = create_engine(CONF.database.connection, echo=False)
    for model in models:
        model.metadata.create_all(engine)
