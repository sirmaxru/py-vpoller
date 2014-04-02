# Copyright (c) 2013-2014 Marin Atanasov Nikolov <dnaeon@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer
#    in this position and unchanged.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR(S) ``AS IS'' AND ANY EXPRESS OR
# IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE AUTHOR(S) BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
# THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
vPoller Agent module for the VMware vSphere Poller

vPoller Agents are used by the vPoller Workers, which take care of
establishing the connection to the vSphere hosts and do all the heavy lifting.

Check the vSphere Web Services SDK API for more information on the properties
you can request for any specific vSphere managed object

    - https://www.vmware.com/support/developer/vc-sdk/

"""

import logging

import zmq
import pyVmomi
from vpoller.core import VPollerException
from vpoller.connector import VConnector

class VSphereAgent(VConnector):
    """
    VSphereAgent class

    Defines methods for retrieving vSphere object properties

    These are the worker agents that do the actual polling from the vSphere host

    Extends:
        VConnector

    """
    def _discover_objects(self, properties, obj_type):
        """
        Helper method to simplify discovery of vSphere managed objects

        This method is used by the '*.discover' vPoller Worker methods and is 
        meant for collecting properties for multiple objects at once, e.g.
        during object discovery operation.

        Args:
            properties          (list): List of properties to be collected
            obj_type   (pyVmomi.vim.*): Type of vSphere managed object

        Returns:
            The discovered objects in JSON format

        """
        logging.info('[%s] Discovering %s managed objects', self.host, obj_type.__name__)

        view_ref = self.get_container_view(obj_type=[obj_type])
        try:
            data = self.collect_properties(
                view_ref=view_ref,
                obj_type=obj_type,
                path_set=properties
            )
        except Exception as e:
            return { 'success': -1, 'msg': 'Cannot collect properties: %s' % e }

        result = {
            'success': 0,
            'msg': 'Successfully discovered objects',
            'result': data,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, result)

        return result

    def _get_object_properties(self, properties, obj_type, obj_property_name, obj_property_value):
        """
        Helper method to simplify retrieving of properties for a single managed object

        This method is used by the '*.get' vPoller Worker methods and is 
        meant for collecting properties for a single managed object.

        We first search for the object with property name and value, then create a
        list view for this object and finally collect it's properties.

        Args:
            properties                  (list): List of properties to be collected
            obj_type           (pyVmomi.vim.*): Type of vSphere managed object
            obj_property_name            (str): Property name used while searching for the object
            obj_property_value           (str): Property value uniquely identifying the object in question

        Returns:
            The collected properties for this managed object in JSON format

        """
        logging.info('[%s] Retrieving properties for %s managed object of type %s',
                     self.host,
                     obj_property_value,
                     obj_type.__name__
        )

        # Find the Managed Object reference for the requested object
        try:
            obj = self.get_object_by_property(
                property_name=obj_property_name,
                property_value=obj_property_value,
                obj_type=obj_type
            )
        except Exception as e:
            return { 'success': -1, 'msg': 'Cannot collect properties: %s' % e }

        if not obj:
            return { 'success': -1, 'msg': 'Cannot find object %s' % obj_property_value }

        # Create a list view for this object and collect properties
        view_ref = self.get_list_view(obj=[obj])

        try:
            data = self.collect_properties(
                view_ref=view_ref,
                obj_type=obj_type,
                path_set=properties
            )
        except Exception as e:
            return { 'success': -1, 'msg': 'Cannot collect properties: %s' % e }

        result = {
            'success': 0,
            'msg': 'Successfully retrieved object properties',
            'result': data,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, result)
        
        return result

    def _object_datastore_get(self, obj_type, name):
        """
        Helper method used for getting the datastores available to an object

        This method searches for the managed object with 'name' and retrieves
        the 'datastore' property which contains all datastores available/used
        by the managed object, e.g. VirtualMachine, HostSystem.

        Args:
            obj_type (pyVmomi.vim.*): Managed object type
            name               (str): Name of the managed object, e.g. host, virtual machine

        Returns:
            The discovered objects in JSON format

        """
        logging.debug('[%s] Getting datastores for %s managed object of type %s',
                      self.host,
                      name,
                      obj_type.__name__
        )

        # Find the object by it's 'name' property and get the datastores available/used by it
        data = self._get_object_properties(
            properties=['name', 'datastore'],
            obj_type=obj_type,
            obj_property_name='name',
            obj_property_value=name
        )

        if data['success'] != 0:
            return data

        # Get the name and datastore properties from the result
        props = data['result'][0]
        obj_name, obj_datastores = props['name'], props['datastore']

        # Get a list view of the datastores available/used by this object and collect properties
        view_ref = self.get_list_view(obj=obj_datastores)
        result = {}
        result['name'] = obj_name
        result['datastore'] = self.collect_properties(
            view_ref=view_ref,
            obj_type=pyVmomi.vim.Datastore,
            path_set=['name', 'info.url']
        )

        r = {
            'success': 0,
            'msg': 'Successfully discovered objects',
            'result': result,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, r)

        return r

    def event_latest(self, msg):
        """
        Get the latest event registered

        Example client message would be:
        
            {
                "method":   "event.latest",
        	"hostname": "vc01.example.org",
            }

        Returns:
            The discovered objects in JSON format

        """
        logging.info('[%s] Retrieving latest registered event', self.host)

        result = {
            'msg': 'Successfully retrieved event',
            'success': 0,
            'result': self.si.content.eventManager.latestEvent.fullFormattedMessage,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, result)

        return result

    def about(self, msg):
        """
        Get the 'about' information for the vSphere host this agent is connected to

        Example client message would be:
        
            {
                "method":   "about",
        	"hostname": "vc01.example.org"
            }

        Example client message requesting additional properties:
        
            {
                "method":   "about",
        	"hostname": "vc01.example.org"
                "properties": [
                    "apiType",
                    "apiVersion",
                    "version"
                ]
            }

        Returns:
            The discovered objects in JSON format

        """
        logging.info("[%s] Retrieving 'about' information", self.host)

        # If no properties are specified just return the 'fullName' property
        if not msg.has_key('properties') or not msg['properties']:
            properties = ['fullName']
        else:
            properties = msg['properties']

        result = {
            'msg': 'Successfully retrieved properties',
            'success': 0,
            'result': {prop:getattr(self.si.content.about, prop, None) for prop in properties}
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, result)

        return result

    def net_discover(self, msg):
        """
        Discover all pyVmomi.vim.Network managed objects

        Example client message would be:
        
            {
                "method":   "net.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "net.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "summary.accessible"
                ]
            }
        
        Returns:
            The discovered objects in JSON format
        
        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.Network)

    def net_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.Network managed object

        Example client message would be:

            {
                "method":     "net.get",
                "hostname":   "vc01.example.org",
                "name":       "VM Network",
                "properties": [
                    "name",
                    "overallStatus"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.Nework,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

    def datacenter_discover(self, msg):
        """
        Discover all pyVmomi.vim.Datacenter managed objects

        Example client message would be:
        
            {
                "method":   "datacenter.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "datacenter.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "overallStatus"
                ]
            }
        
        Returns:
            The discovered objects in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.Datacenter)

    def datacenter_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.Datacenter managed object

        Example client message would be:

            {
                "method":     "datacenter.get",
                "hostname":   "vc01.example.org",
                "name":       "MyDatacenter",
                "properties": [
                    "name",
                    "overallStatus"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.Datacenter,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

    def cluster_discover(self, msg):
        """
        Discover all pyVmomi.vim.ClusterComputeResource managed objects

        Example client message would be:
        
            {
                "method":   "cluster.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "cluster.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "overallStatus"
                ]
            }
              
        Returns:
            The discovered objects in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])
            
        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.ClusterComputeResource)

    def cluster_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.ClusterComputeResource managed object

        Example client message would be:

            {
                "method":     "cluster.get",
                "hostname":   "vc01.example.org",
                "name":       "MyCluster",
                "properties": [
                    "name",
                    "overallStatus"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.ClusterComputeResource,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

    def resource_pool_discover(self, msg):
        """
        Discover all pyVmomi.vim.ResourcePool managed objects

        Example client message would be:
        
            {
                "method":   "resource.pool.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "resource.pool.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "overallStatus"
                ]
            }
              
        Returns:
            The discovered objects in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])
            
        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.ResourcePool)

    def resource_pool_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.ResourcePool managed object

        Example client message would be:

            {
                "method":     "resource.pool.get",
                "hostname":   "vc01.example.org",
                "name":       "MyResourcePool",
                "properties": [
                    "name",
                    "runtime.cpu",
                    "runtime.memory",
                    "runtime.overallStatus"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.ResourcePool,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

    def host_discover(self, msg):
        """
        Discover all pyVmomi.vim.HostSystem managed objects

        Example client message would be:
        
            {
                "method":   "host.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "host.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "runtime.powerState"
                ]
            }
              
        Returns:
            The discovered objects in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.HostSystem)

    def host_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.HostSystem managed object

        Example client message would be:

            {
                "method":     "host.get",
                "hostname":   "vc01.example.org",
                "name":       "esxi01.example.org",
                "properties": [
                    "name",
                    "runtime.powerState"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.HostSystem,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

    def host_vm_get(self, msg):
        """
        Get all Virtual Machines running on this HostSystem 

        Example client message would be:

            {
                "method":     "host.vm.get",
                "hostname":   "vc01.example.org",
                "name":       "esxi01.example.org",
            }
              
        Returns:
            The managed object properties in JSON format

        """
        logging.debug('[%s] Getting VirtualMachine list running on %s host', self.host, msg['name'])
        
        # Find the HostSystem managed object and get the 'vm' property
        data = self._get_object_properties(
            properties=['name', 'vm'],
            obj_type=pyVmomi.vim.HostSystem,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

        if data['success'] != 0:
            return data

        props = data['result'][0]
        host_name, host_vms = props['name'], props['vm']

        # Create a list view for the VirtualMachine managed objects
        view_ref = self.get_list_view(obj=host_vms)
        result = {}
        result['name'] = host_name
        result['vm'] = self.collect_properties(
            view_ref=view_ref,
            obj_type=pyVmomi.vim.VirtualMachine,
            path_set=['name']
        )

        r = {
            'success': 0,
            'msg': 'Successfully discovered objects',
            'result': result,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, r)

        return r

    def host_datastore_get(self, msg):
        """
        Get all Datastores available for a pyVmomi.vim.HostSystem managed object

        Example client message would be:
        
            {
                "method":   "host.datastore.get",
        	"hostname": "vc01.example.org",
                "name":     "esxi01.example.org",
            }

        Returns:
            The discovered objects in JSON format

        """
        return self._object_datastore_get(
            obj_type=pyVmomi.vim.HostSystem,
            name=msg['name']
        )

    def vm_discover(self, msg):
        """
        Discover all pyVmomi.vim.VirtualMachine managed objects

        Example client message would be:
        
            {
                "method":   "vm.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "vm.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "runtime.powerState"
                ]
            }
              
        Returns:
            The discovered objects in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.VirtualMachine)

    def vm_disk_discover(self, msg):
        """
        Discover all disks used by a pyVmomi.vim.VirtualMachine managed object

        Note, that this request requires you to have VMware Tools installed in order
        get information about the guest disks.

        Example client message would be:
        
            {
                "method":   "vm.disk.discover",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org"
            }
        
        Example client message requesting additional properties to be collected:

            {
                "method":   "vm.disk.discover",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org",
                "properties": [
                    "capacity",
                    "diskPath",
                    "freeSpace"
                ]
            }

        Returns:
            The discovered objects in JSON format

        """
        logging.debug('[%s] Discovering guest disks for VirtualMachine %s', self.host, msg['name'])

        # Find the VM and get the guest disks
        data = self._get_object_properties(
            properties=['name', 'guest.disk'],
            obj_type=pyVmomi.vim.VirtualMachine,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

        if data['success'] != 0:
            return data

        # Get the VM name and guest disk properties from the result
        props = data['result'][0]
        vm_name, vm_disks = props['name'], props['guest.disk']

        # Properties to be collected for the guest disks
        properties = ['diskPath']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        # Get the requested disk properties
        result = {}
        result['name'] = vm_name
        result['disk'] = [{prop:getattr(disk, prop, None) for prop in properties} for disk in vm_disks]

        r = {
            'success': 0,
            'msg': 'Successfully discovered objects',
            'result': result,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, r)

        return r

    def vm_net_discover(self, msg):
        """
        Discover information about network adapters on a pyVmomi.vim.VirtualMachine managed object

        Note, that this request requires you to have VMware Tools installed in order
        get information about the guest network adapters.

        Example client message would be:
        
            {
                "method":   "vm.net.discover",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org"
            }
        
        Example client message requesting additional properties to be collected:

            {
                "method":   "vm.net.discover",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org",
                "properties": [
                    "network",
                    "connected",
                    "macAddress",
                    "ipConfig"
                ]
            }

        Returns:
            The discovered objects in JSON format

        """
        logging.debug('[%s] Discovering guest network adapters for VirtualMachine %s', self.host, msg['name'])

        # Find the VM and get the network adapters
        data = self._get_object_properties(
            properties=['name', 'guest.net'],
            obj_type=pyVmomi.vim.VirtualMachine,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

        if data['success'] != 0:
            return data

        # Get the VM name and network adapters properties from the result
        props = data['result'][0]
        vm_name, vm_networks = props['name'], props['guest.net']

        # Properties to be collected for the guest disks
        properties = ['network']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        # Get the requested properties
        result = {}
        result['name'] = vm_name
        result['net']  = [{prop:getattr(net, prop, None) for prop in properties} for net in vm_networks]

        r = {
            'success': 0,
            'msg': 'Successfully retrieved properties',
            'result': result,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, r)

        return r

    def vm_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.VirtualMachine managed object

        Example client message would be:

            {
                "method":     "vm.get",
                "hostname":   "vc01.example.org",
                "name":       "vm01.example.org",
                "properties": [
                    "name",
                    "runtime.powerState"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.VirtualMachine,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

    def vm_host_get(self, msg):
        """
        Get the vSphere host where a Virtual Machine is running on

        Example client message would be:

            {
                "method":     "vm.running.on.host",
                "hostname":   "vc01.example.org",
                "name":       "vm01.example.org",
            }
              
        Returns:
            The managed object properties in JSON format

        """
        logging.debug('[%s] Getting HostSystem where %s VirtualMachine is running on', self.host, msg['name']) 
            
        data = self._get_object_properties(
            properties=['name', 'runtime.host'],
            obj_type=pyVmomi.vim.VirtualMachine,
            obj_property_name='name',
            obj_property_value=msg['name']
        )

        if data['success'] != 0:
            return data

        props = data['result'][0]
        vm_name, vm_host = props['name'], props['runtime.host']

        result = {
            'name': vm_name,
            'host': vm_host.name,
        }

        r = {
            'success': data['success'],
            'msg': data['msg'],
            'result': result,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, r)

        return r

    def vm_datastore_get(self, msg):
        """
        Get all Datastores used by a pyVmomi.vim.VirtualMachine managed object

        Example client message would be:
        
            {
                "method":   "vm.datastore.get",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org",
            }

        Returns:
            The discovered objects in JSON format

        """
        return self._object_datastore_get(
            obj_type=pyVmomi.vim.VirtualMachine,
            name=msg['name']
        )

    def vm_disk_get(self, msg):
        """
        Get properties for a single disk of a pyVmomi.vim.VirtualMachine managed object

        Note, that this request requires you to have VMware Tools installed in order
        get information about the guest disks.

        Example client message would be:
        
            {
                "method":   "vm.disk.get",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org"
                "key":      "/var"
            }
        
        Example client message requesting additional properties to be collected:

            {
                "method":   "vm.disk.get",
        	"hostname": "vc01.example.org",
                "name":     "vm01.example.org",
                "key":      "/var",
                "properties": [
                    "capacity",
                    "diskPath",
                    "freeSpace"
                ]
            }

        Returns:
            The discovered objects in JSON format

        """
        logging.debug(
            '[%s] Getting guest disk info for %s on VirtualMachine %s',
            self.host,
            msg['key'],
            msg['name']
        )
        
        # Discover the VM disks
        data = self.vm_disk_discover(msg)

        if data['success'] != 0:
            return data

        # If we have no key for the disk, just return the result from discovery
        if msg.has_key('key') and msg['key']:
            disk_path = msg['key']
        else:
            return data

        props = data['result']
        disks = props['disk']

        for disk in disks:
            if disk['diskPath'] == disk_path:
                break
        else:
            return { 'success': -1, 'msg': 'Unable to find guest disk %s' % disk_path }

        result = {}
        result['name'] = msg['name']
        result['disk'] = disk

        r = {
            'success': 0,
            'msg': 'Successfully retrieved properties',
            'result': result,
        }

        logging.debug('[%s] Returning result from operation: %s', self.host, r)
        
        return r

    def datastore_discover(self, msg):
        """
        Discover all pyVmomi.vim.Datastore managed objects

        Example client message would be:
        
            {
                "method":   "datastore.discover",
        	"hostname": "vc01.example.org",
            }

        Example client message which also requests additional properties:

            {
                "method":     "datastore.discover",
                "hostname":   "vc01.example.org",
                "properties": [
                    "name",
                    "summary.url"
                ]
            }
              
        Returns:
            The discovered objects in JSON format

        """
        # Property names to be collected
        properties = ['name']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._discover_objects(properties=properties, obj_type=pyVmomi.vim.Datastore)

    def datastore_get(self, msg):
        """
        Get properties of a single pyVmomi.vim.Datastore managed object

        Example client message would be:

            {
                "method":     "datastore.get",
                "hostname":   "vc01.example.org",
                "name":       "ds:///vmfs/volumes/643f118a-a970df28/",
                "properties": [
                    "name",
                    "summary.accessible",
                    "summary.capacity"
                ]
            }
              
        Returns:
            The managed object properties in JSON format

        """
        # Property names to be collected
        properties = ['name', 'info.url']
        if msg.has_key('properties') and msg['properties']:
            properties.extend(msg['properties'])

        return self._get_object_properties(
            properties=properties,
            obj_type=pyVmomi.vim.Datastore,
            obj_property_name='info.url',
            obj_property_value=msg['name']
        )
