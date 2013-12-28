#! /usr/bin/env python
import ipaddress, os, getopt
import sys, re, getpass, argparse, subprocess
from time import sleep
from pysphere import MORTypes, VIServer, VITask, VIProperty, VIMor, VIException
from pysphere.vi_virtual_machine import VIVirtualMachine
from pysphere.resources import VimService_services as VI

def mac_address_generator( ip_address ):
	"""generates a mac address based on the ip address"""
	ip_address_int = int(ip_address)
	ip_list = [ ( ip_address_int / 2** ( 8*octet ) ) % 256 for octet in reversed ( range( 4 ) ) ] # Construct the IP address octets from integer
	mac = ('00:00:%02x:%02x:%02x:%02x' %(ip_list[0],ip_list[1],ip_list[2],ip_list[3]))    #Construct the mac address
	return mac

def write_dhcpd_conf( mac, ip, hostname, filename): 
	with open(filename, 'a') as out1:
		out1.write ('host %s {\n' %(hostname))
		out1.write ('hardware ethernet %s;\n' %(mac))
                out1.write ('fixed-address %s;\n' %(ip))
		out1.write ('option host-name "%s";\n' %(hostname))
                out1.write ('filename "esx/pxelinux.0";\n')
		out1.write ('}\n')
		return 1

def find_vm(con, name):
        try:
                vm = con.get_vm_by_name(name)
                return vm
        except VIException:
                return None

def spawn_esx_vm(con, template, hostname, mac ):
	# Here we fetch the vm by its name #
	template_vm = find_vm(con, template)
	# template_vm = con.get_vm_by_name(template)
	print 'template vm is %s' %template_vm
	print 'new vm is %s' %hostname
	print 'mac is %s' %mac
	print ('Trying to clone %s to VM %s' % (template_vm,hostname))
	print template_vm
	print ('================================================================================')
	# Does the VM already exist? #
	if find_vm(con, hostname):
                print 'ERROR: %s already exists' % hostname
	else:
		clone = template_vm.clone(hostname, True, None, None, None, None, False)
		print ('VM %s created' % (hostname))

	# And now we need to change its MAC address. We expect to find two Vmxnet3 devices#
	interfaces = []
	macs = []
	# Query network interfaces from vCenter and put them into a list called "interfaces"
	for dev in clone.properties.config.hardware.device:
		if dev._type in ["VirtualVmxnet3"]:
			interfaces.append(dev._obj)

	#Put the mac addresses into a list.
	macs.append(mac)
	
	#Cycle through the interfaces.
	for interface, mac in zip(interfaces, macs):
		print interface
		interface.set_element_addressType("Manual")
		interface.set_element_macAddress(mac)

		#Invoke ReconfigVM_Task 
		request = VI.ReconfigVM_TaskRequestMsg()
		_this = request.new__this(clone._mor)
		_this.set_attribute_type(clone._mor.get_attribute_type())
		request.set_element__this(_this)
		spec = request.new_spec()
		dev_change = spec.new_deviceChange()
		dev_change.set_element_device(interface)
		dev_change.set_element_operation("edit")
		spec.set_element_deviceChange([dev_change])
		request.set_element_spec(spec)
		ret = con._proxy.ReconfigVM_Task(request)._returnval

		#Wait for the task to finish 
		task = VITask(ret, con)

		status = task.wait_for_state([task.STATE_SUCCESS, task.STATE_ERROR])
		if status == task.STATE_SUCCESS:
		    print "VM successfully reconfigured"
		elif status == task.STATE_ERROR:
		    print "Error reconfiguring vm:", task.get_error_message()

def main(argv):

	kill_me_now=0
	try:
		opts, args = getopt.getopt(argv,"hf:",["file="])
	except getopt.GetoptError:
		print 'spawn_esx.py -f <inputfile>'
		sys.exit(2)
	# parse the command line arguments.
	for opt, arg in opts:
		if opt == '-h':
			print 'test.py -i <inputfile> -o <outputfile>'
			sys.exit()
		elif opt in ("-f", "--ifile"):
			inputfile = arg
	
	print "Checking input file exists"
	if not os.path.exists(inputfile):
		print 'ERROR: %s does not exist' % inputfile
		kill_me_now = 1
	
	### Connect to vCenter ###
	con = VIServer()
        con.connect('10.1.1.47','be_a.holway','X9de!X9de!')

	with open(inputfile) as inf:
		line_words = (line.split(';') for line in inf)
		# check if VMs with this name allready exist in the vCenter.
		for x in line_words:
			hostname = x[1]
			if find_vm(con, hostname):
				print 'ERROR: %s already exists' % hostname
				kill_me_now = 1
		
		# if any of the VMs exist in the vcenter, exit.
		if kill_me_now == 1:
                        print "There were errors with the input file"
                        sys.exit()
		else:
			print "Thed Mighty Alien mother shivers as she prepares to birth her children."
                        print "Begining spawning."
		
		# this is where the action starts.	
        with open(inputfile) as inf:
                line_words = (line.split(';') for line in inf)
		for y in line_words:
			print y
			y[2] = unicode(y[2])
			ip = ipaddress.IPv4Address(y[2])
			y[3] = unicode(y[3])
			network = ipaddress.ip_network(y[3])
			# this checks that the ip address is actually in the subnet.
			if ip in network:
				filename = str(network)
				print filename
				# here we remove the "/" from the network and replace it with a "-" so we can use it as a filename. 
				filename = filename.replace('/','-')
				print filename
				# work out where we will put the dhcpd config for the currently processing VM.
				filename = '/etc/dhcp/dhcpd.conf.%s' %(filename)
				hostname = y[1]
				# generate a mac address from the ip.
				mac = mac_address_generator(ip)
				template = x[0]
				print 'cloning %s to %s with ip %s' %(template,y[1],y[2])
				write_dhcpd_conf(mac, ip, hostname, filename)
				# restart dhcpd.
				os.system("/etc/init.d/dhcpd restart")
				spawn_esx_vm ( con, template, hostname , mac )

if __name__ == "__main__":
	main(sys.argv[1:]) # [1:] slices off the first argument which is the name of the program
