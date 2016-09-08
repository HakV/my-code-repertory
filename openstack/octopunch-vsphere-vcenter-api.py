# Copyright 2012-2013 Beijing Huron Technology Co.Ltd.
#
# Author: Fan Guiju <fanguiju@hihuron.com>
#                                                                                           
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See
# the
# License for the specific language governing permissions and limitations
# under the License.
from octopunch.db import base

class API(base.Base):
    """API for handling vcenter resources."""

    def __init__(self):
        super(API, self).__init__()

    
    def vcenter_list(self, context, filters=None):
        """Get vcenter list.
        
        :param context: class:`RequestContext` instance
        
        :param filters: select data by filter.
        :type: ``dict``
        
        :return: return a list of class:`VenterInfo` instance
        """
        return self.db.vcenter_get_all(context, filters)


    def vcenter_get(self, context, uuid):
        """Get a vcenter.
        
        :param context: class:`RequestContext` instance
        
        :param uuid: uuid of vcenter.
        
        :return: return a class:`VcenterInfo` instance
        """
        return self.db.vcenter_get(context, uuid)


    def vcenter_create(self, context, values):
        """Create a vcenter.
        
        :param context: class:`RequestContext` instance
        
        :param values; values of vcenter.
        
        :return: return a class:`VcenterInfo` instance
        """
        return self.db.vcenter_create(context, values)


    def vcenter_delete(self, context, uuid):
        """Delete a vcenter.
        
        :param context: class:`RequestContext` instance
        
        :param uuid: uuid of vcenter.
        :type: ``str``
        """
        return self.db.vcenter_delete(context, uuid)


    def vcenter_update(self, context, uuid, body=None):
        """Update a vcenter.
        
        :param context: class:`RequestContexe` instance
        
        :param uuid: uuid of vcenter.
        :type:``str``
        
        :param body: The content if the update
        :type:``dict``
        
        :return: return a class:`VcenterInfo` instance"""
        return self.db.vcenter_update(content, uuid, body)






