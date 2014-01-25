#
#  SMDR Logger for the Inter-Tel AXXESS system
#  
#  Author: William Deacon
#  Date: Apr 24, 2013
#

import serial
import io
import re
import sys
import getopt
import logging

from Cheetah.Template import Template
from datetime import date
from datetime import timedelta
from os import path
from time import sleep

# -----------------------------------------------
#   SMDR record object
# -----------------------------------------------
class Record:
	def __init__( self, type, extn, trunk, dialed, did, time, duration, cost, account, star ):
		self.type = type
		self.extn = extn
		self.trunk = trunk
		self.dialed = dialed
		self.did = did
		self.time = time
		self.duration = duration
		self.cost = cost
		self.account = account
		self.star = star

# -----------------------------------------------
#   MAIN Loop
# -----------------------------------------------
def main( argv ):

	# Establish sane defaults for our program
	port = 'COM1'				# default serial port
	baud = 9600					# default baudrate
	logfile = 'smdr-log.txt'	# default logfile path
	loglevel = logging.INFO		# default logging level
	
	# Process our starting arguments
	try:
		opts, args = getopt.getopt( argv, 'hdp:b:l:' )
	except getopt.GetoptError:
		print 'Usage: smdr.py [-h] [-p serialport] [-b baudrate] [-l logfile] [-d]'
		print '  -h               Display this help message'
		print '  -p serialport    Select a serial port to attach to (default COM1)'
		print '  -b baudrate      Baudrate for the serial connection (default 9600)'
		print '  -l logfile       Path and filename for logfile (default smdr-log.txt)'
		print '  -d               Enable debugging level logging'
		sys.exit()
	
	for opt, arg in opts:
		if opt == '-h':
			print 'Usage: smdr.py [-h] [-p serialport] [-b baudrate] [-l logfile] [-d]'
			print '  -h               Display this help message'
			print '  -p serialport    Select a serial port to attach to (default COM1)'
			print '  -b baudrate      Baudrate for the serial connection (default 9600)'
			print '  -l logfile       Path and filename for logfile (default smdr-log.txt)'
			print '  -d               Enable debugging level logging'
			sys.exit()

		elif opt == '-d':
			loglevel = logging.DEBUG
		
		elif opt == '-p':
			port = arg

		elif opt == '-b':
			baud = arg
			
		elif opt == '-l':
			logfile = arg
	
	# Set up logging
	logging.basicConfig( filename = logfile, format = '%(asctime)s %(levelname)s: %(message)s',
	                     datefmt = '%Y-%m-%d %H:%M:%S', level = loglevel )
	logging.info( 'Starting SMDR processing' )
	logging.info( 'Opening %s at %s baud for processing', port, baud )
	if loglevel == logging.DEBUG:
		logging.info( 'Debug logging is ON' )
	else:
		logging.info( 'Debug logging is OFF' )
	
	
	# Establish a new serial connection to PORT
	# and wrap the serial port in a RW Buffer
	try:
		ser = serial.Serial( port, baud, timeout=1 )
		sio = io.TextIOWrapper( io.BufferedRWPair( ser, ser ) )
	except serial.SerialException, e:
		logging.critical( 'Failed to open serial connection to %s', port )
		sys.exit( 1 )
	
	# Loop forever collectiong record statements
	while True:
	
		# If there's no line to collect, wait 5 seconds and try again!
		line = sio.readline()
		while not line:
			sleep( 5 )
			line = sio.readline()

		# Create a record object from our input and log it
		record = processRecord( line )
		if record != None:
			updateLogs( record )
	
	# We should never get here.  But if we do, be nice!
	logging.error( 'Abnormal termination of processing' )
	ser.close()
	sys.exit( 2 )

# -----------------------------------------------
#   Convert a raw SERIAL entry into usable data
# -----------------------------------------------
def processRecord( record ):
	# Every line received will be either a header line, or an 80 char line
	# with the following characteristics:
	#
	# RECORD FORMAT FOR AXXESS SMDR
	#  1- 3: Type of phone call
	#  4- 9: Extention dialed FROM
	# 10-15: Trunk ID used
	# 16-44: Digits dialed
	# 45-50: Start time of call
	# 51-59: Duration of call in seconds (S=XXX)
	# 60-66: Calculated cost of call
	# 67-78: Account code used, if any
	#    80: '*' if inital call?
	
	# Is it a blank line?
	record = record.strip()
	if record == '':
		return None
	
	# Does it match a "Station" header?
	m = re.match( r'Station', record )
	if m is not None:
		return None
	
	# Does it match a column header line?
	m = re.match( r'TYP', record )
	if m is not None:
		return None

	# Is it an SMDR record?
	regex = ( r'(?P<Type>\w+?)\s+?(?P<Extn>\w+?)\s+?(?P<TrunkID>\w+?)\s+?'
      '(?P<Dialed>[#0-9-]+?)\s+?(?P<DID>[0-9-]+?)?\s+?'
      '(?P<Start>\d\d:\d\d)\s+?(?P<Duration>S=\d+?)\s+?'
      '(?P<Cost>\$\d\d\.\d\d)\s*?(?P<Account>\d+?)?\s*?(?P<Star>\*)?$' )

	m = re.match( regex, record )
	if m is None:
		logging.warning( 'Couldn\'t match output line as valid input' )
		logging.warning( 'Line was %s', record )
		return None
	
	# Clean up our data
	# Strip off the 'S=' of duration and convert it into h:m:s
	g = m.groupdict()
	g['Duration'] = g['Duration'][2:]
	g['Duration'] = str( timedelta( seconds = int(g['Duration']) ) )
	
	logging.debug( 'Processed Line: %s', record )
	logging.debug( 'Processed Line: %s', g )
	
	return Record( g['Type'], g['Extn'], g['TrunkID'], g['Dialed'], g['DID'],
               g['Start'], g['Duration'], g['Cost'], g['Account'], g['Star'] )

# -----------------------------------------------
#   Log a RECORD into HTML and CSV files
# -----------------------------------------------
def updateLogs( record ):
	
	rotateFlag = False
	
	# Get current timestamp
	now = date.today()
	
	# Generate the logname
	dailylogname = now.strftime( 'smdr-' + now.strftime( '%Y-%m-%d' ) )
	monthlylogname = now.strftime( 'smdr-' + now.strftime( '%Y-%m' ) )
	
	# Check to see if HTML log exists for today
	if path.isfile( 'logs/html/' + dailylogname + '.html' ):
		fd = open( 'logs/html/' + dailylogname + '.html', 'a' )
	else:
		# Load HTML log template
		s = { 'date' : now.strftime( '%b %d, %Y' ) }
		t = Template( file='resources/templates/htmlview.tmpl', searchList=[s] )
		
		# Create today's HTML logfile and populate it with the template
		fd = open( 'logs/html/' + dailylogname + '.html', 'w' )
		fd.write( str(t) )
		
		# Set flag to update our index
		rotateFlag = True
	
	printHTMLLog( record, fd )
	fd.close()
	
	# Check to see if CSV Daily log exists for today
	if path.isfile( 'logs/csv/daily/' + dailylogname + '.csv' ):
		fd = open( 'logs/csv/daily/' + dailylogname + '.csv', 'a' )
	else:
		fd = open( 'logs/csv/daily/' + dailylogname + '.csv', 'w' )
		fd.write( 'SMDR Logger Date, ' + now.strftime( '%B %d, %Y' ) + '\n' )
		fd.write( 'Date, Type, Extention, Digits Dialed, DID Number, Start Time, Duration, Account Code\n' )
		fd.flush()
		
		# Set flag to update our index
		rotateFlag = True
	
	printCSVLog( record, fd )
	fd.close()
	
	# Check to see if CSV Monthly log exists for today
	if path.isfile( 'logs/csv/monthly/' + monthlylogname + '.csv' ):
		fd = open( 'logs/csv/monthly/' + monthlylogname + '.csv', 'a' )
	else:
		fd = open( 'logs/csv/monthly/' + monthlylogname + '.csv', 'w' )
		fd.write( 'SMDR Logger Date, ' + now.strftime( '%B, %Y' ) + '\n' )
		fd.write( 'Date, Type, Extention, Digits Dialed, DID Number, Start Time, Duration, Account Code\n' )
		fd.flush()

		# Set flag to update our index
		rotateFlag = True
	
	printCSVLog( record, fd )
	fd.close()	

	# If we created a new file, we need to update our index!
	if rotateFlag == True:

		if path.isfile( 'logs/html/index.html' ):
			fd = open( 'logs/html/index.html', 'a' )
		else:
			t = Template( file='resources/templates/index.tmpl' )
			fd = open( 'logs/html/index.html', 'w' )
			fd.write( str(t) )
			fd.flush()
		
		printIndexLine( fd )
		fd.close()
	
	
# -----------------------------------------------
#   Print record into the HTML log file
# -----------------------------------------------
def printHTMLLog( record, filehandle ):
	filehandle.write( '<tr>\n' )
	
	if record.type == 'IN':
		filehandle.write( '<td><img src="../../resources/icons/incoming.png"></td>' )
	elif record.type == 'TLC' or record.type == 'TLD' or record.type == 'LOC':
		filehandle.write( '<td><img src="../../resources/icons/outgoing.png"></td>' )
	else:
		filehandle.write( '<td></td>' )

	filehandle.write( '<td>' + str( record.type ) + '</td>\n' )
	filehandle.write( '<td>' + str( record.extn ) + '</td>\n' )
	filehandle.write( '<td>' + str( record.dialed ) + '</td>\n' )
	filehandle.write( '<td>' + str( record.did ) + '</td>\n' )
	filehandle.write( '<td>' + str( record.time ) + '</td>\n' )
	filehandle.write( '<td>' + str( record.duration ) + '</td>\n' )
	filehandle.write( '<td>' + str( record.account ) + '</td>\n' )
	filehandle.write( '</tr>\n' )
	filehandle.flush()

# -----------------------------------------------
#   Print record into the CSV log file
# -----------------------------------------------
def printCSVLog( record, filehandle ):
	d = date.today()
	filehandle.write( d.strftime( '%Y-%m-%d' ) + ', ' )
	filehandle.write( str( record.type ) + ', ' )
	filehandle.write( str( record.extn ) + ', ' )
	filehandle.write( str( record.dialed ) + ', ' )
	filehandle.write( str( record.did ) + ', ' )
	filehandle.write( str( record.time ) + ', ' )
	filehandle.write( str( record.duration ) + ', ' )
	filehandle.write( str( record.account ) + '\n' )
	filehandle.flush()

# -----------------------------------------------
#   Print record into the HTML INDEX file
# -----------------------------------------------
def printIndexLine( filehandle ):
	d = date.today()
	filehandle.write( '<tr>' )
	filehandle.write( '<td><a href="smdr-' + d.isoformat() + '.html">' + d.strftime('%d %b %Y') + '</a></td>' )
	filehandle.write( '<td><a href="smdr-' + d.isoformat() + '.html">View</a></td>' )
	filehandle.write( '<td><a href="../csv/daily/smdr-' + d.isoformat() + '.csv">CSV/Excel</a></td>' )
	filehandle.write( '<td><a href="../csv/monthly/smdr-' + d.strftime('%Y-%m') + '.csv">CSV/Excel</a></td>' )
	filehandle.write( '</tr>\n' )
	filehandle.flush()

if __name__=="__main__":
	main( sys.argv[1:] )
