# Copyright 2012 OpenStack Foundation
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
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer
from sqlalchemy import MetaData, String, Table

from octopunch.i18n import _LE
from oslo_log import log as logging


LOG = logging.getLogger(__name__)


def define_tables(meta):
    vcenters = Table(
        'vcenters', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True),
        Column('vc_value', String(length=255)),
        Column('name', String(length=255)),
        Column('vcs_ip', String(length=255), nullable=False),
        Column('username', String(length=255), nullable=False),
        Column('password', String(length=255), nullable=False),
        mysql_engine='InnoDB'
    )

    datacenters = Table(
        'datacenters', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('dc_value', String(length=255)),
        Column('name', String(length=255)),
        Column('vcenter_uuid', String(length=45), ForeignKey('vcenters.uuid'),
               nullable=False),
        mysql_engine='InnoDB'
    )

    clusters = Table(
        'clusters', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('cls_value', String(length=255)),
        Column('name', String(length=255)),
        Column('overall_cpu_count', Integer),
        Column('overall_cpu_mhz', Integer),
        Column('overall_mem_sizemb', Integer),
        Column('overall_storage_sizemb', Integer),
        Column('datacenter_uuid', String(length=45),
               ForeignKey('datacenters.uuid'), nullable=False),
        mysql_engine='InnoDB'
    )

    resource_pools = Table(
        'resource_pools', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('res_value', String(length=255)),
        Column('name', String(length=255)),
        Column('res_type', String(length=255)),
        Column('res_overall_cpu_count', Integer),
        Column('res_overall_cpu_mhz', Integer),
        Column('res_overhead_cpu_mhz', Integer),
        Column('res_overall_mem_sizemb', Integer),
        Column('res_overhead_mem_sizemb', Integer),
        Column('cluster_uuid', String(length=45), ForeignKey('clusters.uuid'),
               nullable=False),
        mysql_engine='InnoDB'
    )

    hosts = Table(
        'hosts', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('host_value', String(length=255)),
        Column('name', String(length=255)),
        Column('host_ip', String(length=255), nullable=False),
        Column('hardware_cpu_count', Integer),
        Column('hardware_cpu_mhz', Integer),
        Column('overhead_cpu_mz', Integer),
        Column('hardware_mem_sizemb', Integer),
        Column('overhead_mem_sizemb', Integer),
        Column('hardware_nic_count', Integer),
        Column('state_power', String(length=255)),
        Column('state_connect', Boolean),
        Column('cluster_uuid', String(length=45),
               ForeignKey('clusters.uuid')),
        Column('resource_pool_uuid', String(length=45),
               ForeignKey('resource_pools.uuid')),
        mysql_engine='InnoDB'
    )

    virtual_machines = Table(
        'virtual_machines', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('vm_value', String(length=255)),
        Column('name', String(length=255)),
        Column('guest_os', String(length=255)),
        Column('vdisk_count', Integer),
        Column('vdisk_sizemb', Integer),
        Column('vcpu_count', Integer),
        Column('vcpu_mhz', Integer),
        Column('vcpu_overhead_mhz', Integer),
        Column('men_sizemb', Integer),
        Column('men_overhead_sizemb', Integer),
        Column('state_vm_power', String(length=255)),
        Column('guest_nic_count', Integer),
        Column('project_id', String(length=255), nullable=False),
        Column('user_id', String(length=255), nullable=False),
        Column('host_uuid', String(length=45), ForeignKey('hosts.uuid'),
               nullable=False),
        mysql_engine='InnoDB'
    )

    datastores = Table(
        'datastores', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('ds_value', String(length=255)),
        Column('name', String(length=255)),
        Column('ds_type', String(length=255)),
        Column('url', String(length=255)),
        Column('access_mode', String(length=255)),
        Column('accessible', Boolean),
        Column('state_mount', Boolean),
        Column('capacity_sizemb', Integer),
        Column('free_space_sizemb', Integer),
        mysql_engine='InnoDB'
    )

    vstd_switchs = Table(
        'vstd_switchs', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('vsh_value', String(length=255)),
        Column('name', String(length=255)),
        Column('port_count', Integer),
        Column('mtu_count', Integer),
        Column('phy_adapter_name', String(length=255)),
        Column('host_uuid', String(length=45), ForeignKey('hosts.uuid'),
               nullable=False),
        mysql_engine='InnoDB'
    )

    networks = Table(
        'networks', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('net_value', String(length=255)),
        Column('name', String(length=255), nullable=False),
        Column('ip_pool', String(length=255)),
        mysql_engine='InnoDB'
    )

    guest_nics = Table(
        'guest_nics', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('uuid', String(length=45), primary_key=True, nullable=False),
        Column('gn_value', String(length=255)),
        Column('ip_address', String(length=255)),
        Column('mac_address', String(length=255)),
        Column('state_connect', Boolean),
        Column('virtual_machine_uuid', String(length=45),
               ForeignKey('virtual_machines.uuid'), nullable=False),
        mysql_engine='InnoDB'
    )

    hosts_datastores = Table(
        'hosts_datastores', meta,
        Column('host_uuid', String(length=45), ForeignKey('hosts.uuid')),
        Column('datastore_uuid', String(length=45),
               ForeignKey('datastores.uuid')),
        mysql_engine='InnoDB'
    )

    virtual_machines_datastores = Table(
        'virtual_machines_datastores', meta,
        Column('virtual_machine_uuid', String(length=45),
               ForeignKey('virtual_machines.uuid')),
        Column('datastore_uuid', String(length=45),
               ForeignKey('datastores.uuid')),
        mysql_engine='InnoDB'
    )

    virtual_machines_networks = Table(
        'virtual_machines_networks', meta,
        Column('virtual_machine_uuid', String(length=45),
               ForeignKey('virtual_machines.uuid')),
        Column('network_uuid', String(length=45),
               ForeignKey('networks.uuid')),
        mysql_engine='InnoDB'
    )

    hosts_networks = Table(
        'hosts_networks', meta,
        Column('host_uuid', String(length=45), ForeignKey('hosts.uuid')),
        Column('network_uuid', String(length=45),
               ForeignKey('networks.uuid')),
        mysql_engine='InnoDB'
    )

    # Note the order relationship between parent and child table
    return [vcenters, datacenters, clusters, resource_pools, hosts,
            virtual_machines, vstd_switchs, guest_nics, datastores,
            networks, hosts_datastores, hosts_networks,
            virtual_machines_datastores, virtual_machines_networks]


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    # create all tables
    # Take care on create order for those with FK dependencies
    tables = define_tables(meta)

    for table in tables:
        try:
            table.create()
        except Exception:
            LOG.info(repr(table))
            LOG.exception(_LE('Exception while creating table.'))
            raise

    if migrate_engine.name == "mysql":
        tables = ['vcenters', 'datacenters', 'clusters',
                  'resource_pools', 'hosts', 'virtual_machines',
                  'datastores', 'vstd_switchs', 'networks', 'guest_nics',
                  'hosts_datastores', 'virtual_machines_datastores',
                  'virtual_machines_networks', 'hosts_networks']
        migrate_engine.execute("SET foreign_key_checks = 0")
        for table in tables:
            migrate_engine.execute(
                "ALTER TABLE %s CONVERT TO CHARACTER SET utf8" % table)
        migrate_engine.execute("SET foreign_key_checks = 1")
        migrate_engine.execute(
            "ALTER DATABASE %s DEFAULT CHARACTER SET utf8" %
            migrate_engine.url.database)
        migrate_engine.execute("ALTER TABLE %s Engine=InnoDB" % table)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    tables = define_tables(meta)
    tables.reverse()
    for table in tables:
        table.drop()
