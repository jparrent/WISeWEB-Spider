#!/usr/bin/python

"""
==================================================================================
title           :wiserep-spider.py
description     :Scrapes and downloads all publicly availabe spectra from WISeREP.
author          :Jerod Parrent
date            :2016-07-06
version         :0.1
usage           :python wiserep-spider.py
notes           :runtime with pages saved and no exlusions = 18.7 hours
python_version  :2.7.12 
==================================================================================

TO-DO, refactor to:
items.py
pipelines.py
settings.py
wiseweb-spider.py

and functions:
getObjHeader(), etc

and Python3
"""

import os, sys, time, pickle
import re, unicodedata, itertools
import urllib, urllib2, requests, mechanize, html2text, cookielib
from collections import OrderedDict
from bs4 import BeautifulSoup

reload(sys) #uncouth
#not needed for python 3
sys.setdefaultencoding('utf8') #uncouth

#set path for new directories
_PATH = os.getcwd()
_DIR_WISEREP = "/sne-external-WISEREP/"
_DIR_INTERNAL = "/sne-internal/"

#used for locating filenames with only these extensions (no fits files)
_ASCII_URL = "\.(flm|dat|asc|asci|ascii|txt|sp|spec)$"

if not os.path.exists(_PATH+_DIR_WISEREP):
	os.mkdir(_PATH+_DIR_WISEREP)

if not os.path.exists(_PATH+_DIR_INTERNAL):
	os.mkdir(_PATH+_DIR_INTERNAL)

#WISeREP Objects Home
_WISEREP_OBJECTS_URL = 'http://wiserep.weizmann.ac.il/objects/list'

#list of non-supernovae to exclude
exclude_type = [
'Afterglow',
'LBV',
'ILRT',
'Nova',
'CV',
'Varstar',
'AGN',
'Galaxy',
'QSO',
'Std-spec',
'Gap',
'Gap I',
'Gap II',
'SN impostor',
'TDE',
'WR',
'WR-WN',
'WR-WC',
'WR-WO',
'Other',
''
]

#list of SN survey programs to exclude, assuming they have already been collected
exclude_program = [
'HIRES',
'SUSPECT',
'BSNIP',
'CSP',
'UCB-SNDB',
'CfA-Ia',
'CfA-Ibc'
'SNfactory',
'HIRES'
]

# exclude_program = ['HIRES']

#dig up list of known non-supernovae, or create if it does not exist
if os.path.exists(_PATH+_DIR_INTERNAL+'non_SN.pickle'):
	with open(_PATH+_DIR_INTERNAL+'non_SN.pickle', 'rb') as pickle_in:
		non_SN = pickle.load(pickle_in)
else:
	non_SN = []

#dig up completed list of events, or create if it does not exist
if os.path.exists(_PATH+_DIR_INTERNAL+'completed.pickle'):
	with open(_PATH+_DIR_INTERNAL+'completed.pickle', 'rb') as pickle_in:
		completed = pickle.load(pickle_in)
else:
	completed = []

#locate objects search form
def select_obj_form(form):
	  return form.attrs.get('action', None) == '/objects/list'

#update non-supernova list pickle
def updateNonSNPickle(SNname, SNlist):
	SNlist.append(SNname)
	with open(_PATH+_DIR_INTERNAL+'non_SN.pickle', 'wb') as pickle_out:
		pickle.dump(SNlist, pickle_out)
		pickle_out.close()

#update completed list pickle
def updateCompletedPickle(SNname, SNlist):
	SNlist.append(SNname)
	with open(_PATH+_DIR_INTERNAL+'completed.pickle', 'wb') as pickle_out:
		pickle.dump(SNlist, pickle_out)
		pickle_out.close()		

def savePage(name, page):
	with open(_PATH+_DIR_INTERNAL+'WISEREP-'+name+'.html', 'w') as f:
		f.write(page)
		f.close()

#begin scraping
start_time = time.time()

r = requests.get(_WISEREP_OBJECTS_URL)
soup = BeautifulSoup(r.content,"lxml")
if r:
	print 'Grabbing list of events from WISeREP'

#grab object name list
SN_list_tags = soup.find("select", {"name":"objid"}).find_all("option")[1:] #remove `Select Option' from list

#Begin by selecting event, visiting page, and scraping.
# SNname_list = ['SN2012fr', 'SN2016com']
# for SNname in SNname_list:	
for item in SN_list_tags:

	SNname = item.get_text()
	if SNname in non_SN:
		print SNname, 'is not a supernova -- Skipping'
		continue
	elif SNname in completed:
		print SNname, 'already done'
		continue

 	print 'Searching for', SNname, '...'

 	#reset for every event -- change if needed
	SN_dict = {} 

	# Browser
	br = mechanize.Browser()

	# Cookie Jar
	cj = cookielib.LWPCookieJar()
	br.set_cookiejar(cj)

	# Browser options
	br.set_handle_equiv(True)
	#br.set_handle_gzip(True)
	br.set_handle_redirect(True)
	br.set_handle_referer(True)
	br.set_handle_robots(False)

	# Follows refresh 0 but not hangs on refresh > 0
	br.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(), max_time=1)

	# User-Agent (this is cheating, ok?)
	br.addheaders = [('User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1')]

	# The site we will navigate into, handling its session
	br.open(_WISEREP_OBJECTS_URL)

	#ready search form with field entries and submit
	br.select_form(predicate=select_obj_form)
	br.form['name'] = SNname
	br.form['rowslimit'] = '1000'
	br.submit()

	#results page
	results_page = br.response().read()
	soup = BeautifulSoup(results_page,"lxml")
	print '\tPage received'

	#locate object header indecies (_idx)
	try:
		headers = soup.find("tr",{"style":"font-weight:bold"}).findChildren("td")
	except AttributeError:
		updateCompletedPickle(SNname,completed)
		print '\t', SNname, 'has no available spectra'
		with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
			f.write('From statement 1: ' + SNname + ' has no spectra to collect' + '\n')
			f.close()
		continue

	for i, header in enumerate(headers):
		if header.text == 'Obj. Name':
			obj_name_idx = i
		if header.text == 'IAUName':
			iau_name_idx = i
		if header.text == 'Redshift':
			redshift_idx = i
		if header.text == 'Type':
			type_idx = i
		if header.text == 'No. ofSpectra': #ofSpectra not a typo
			num_total_spec_idx = i

	#locate objects returned -- it's not always one
	obj_list = soup.findAll("form",{"target":"new"})
	num_objs = len(obj_list)
	if num_objs != 1:
		with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
			f.write(str(num_objs) + ' objects returned for ' + SNname + '\n')
			f.close()

	#locate darkred text ``Potential matching IAU-Name'' if it exists
	#the location of html table rows (tr) changes if it exists
	darkred = soup.find("span", text = " Potential matching IAU-Name/s:", attrs = {"style":"color:darkred; font-size:small"})	

	#parse obj_list, match to SNname, and find its spectra
	for obj in obj_list:
		obj_header = obj.parent.findChildren("td")
		obj_name = obj_header[obj_name_idx].text

		if SNname == obj_name:
			target = obj_header

			if darkred:
				try:
					target_spectra = obj.parent.nextSibling.nextSibling.findChildren("tr",{"valign":"top"})
				except AttributeError:
					print '\t', SNname,'has no spectra to collect'
					with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
						f.write('From statement 2: ' + SNname + ' has no spectra to collect' + '\n')
						f.close()
					continue

			elif darkred == None:
				try:
					target_spectra = obj.parent.nextSibling.findChildren("tr",{"valign":"top"})
				except AttributeError:
					print '\t', SNname,'has no spectra to collect'
					with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
						f.write('From statement 2: ' + SNname + ' has no spectra to collect' + '\n')
						f.close()

	#exclude non-SN
	SNtype = target[type_idx].text
	if SNtype in exclude_type:
		updateNonSNPickle(SNname, non_SN)
		updateCompletedPickle(SNname,completed)
		print '\t', SNname, 'is a', SNtype
		with open(_PATH+_DIR_WISEREP+'non-supernovae.txt', 'a') as f:
			f.write(SNname + ' is a ' + SNtype + '\n')
			f.close()		
		continue

	#second chance to exclude events without spectra
	num_total_spec = target[num_total_spec_idx].text
	num_total_spec = unicodedata.normalize("NFKD",num_total_spec)
	if num_total_spec == u'  ' or num_total_spec == u' 0 ':
		updateCompletedPickle(SNname,completed)
		print '\t', SNname,'has no spectra to collect'
		with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
			f.write('From statement 3: ' + SNname + ' has no spectra to collect' + '\n')
			f.close()
		continue		

	redshift = target[redshift_idx].text
	#z = target[redshift_idx].text
	#redshift = 'Unavailable' if z==u'' else z

	SN_dict[SNname] = OrderedDict()
	#number of private spectra
	num_private_spectra = 0
	#number of publicly available spectra
	num_pub_spectra = 0

	spec_header = soup.find("tr", {"style":"color:black; font-size:x-small"}).findChildren("td")
	for i, header in enumerate(spec_header):
		if header.text == 'Spec. Prog.':
			program_idx = i
		if header.text == 'Instrument':
			instrument_idx = i
		if header.text == 'Observer':
			observer_idx = i
		if header.text == 'Obs.date':
			obsdate_idx = i
		if header.text == 'Ascii/Fits Files':
			filename_idx = i
		if header.text == 'Publish':
			publish_idx = i
		if header.text == 'Contrib':
			contrib_idx = i
		if header.text == 'Last-modified':
			last_mod_idx = i
		if header.text == 'Modified-by':
			modified_by_idx = i

	#build SN_dict and locate ascii files on search results page associated with SNname
	spectrum_haul = OrderedDict()

	for spec in target_spectra:

		spec_link = spec.find("a", href=re.compile(_ASCII_URL))

		try:
			dat_url = urllib.quote(spec_link.attrs['href'],"http://")
		except AttributeError:
			#found private spectrum
			num_private_spectra += 1
			continue

		children = spec.findChildren("td")
		filename = spec_link.text
		program = children[program_idx].text
		if program in exclude_program:
			print '\tSkipping', program, 'spectrum'
			#but still count it as public
			num_pub_spectra += 1
			continue

		#list of duplicate file prefixes to be excluded
		#list not shorted to ['t', 'f', 'PHASE'] for sanity
		regexes = [
		't'+SNname,
		'tPSN',
		'tPS',
		'tLSQ',
		'tGaia',
		'tATLAS',
		'tASASSN',
		'tSMT',
		'tCATA',
		'tSNhunt',
		'tSNHunt',
		'fSNhunt',
		'tSNHiTS',
		'tCSS',
		'tSSS',
		'tCHASE',
		'tSN',
		'tAT',
		'fPSN',
		'PHASE'
		]

		regexes = "(" + ")|(".join(regexes) + ")"
		if re.match(regexes, filename):
			status = 'rapid'
		else:
			status = 'final'

		instrument = children[instrument_idx].text
		observer = children[observer_idx].text
		obsdate = children[obsdate_idx].text
		last_modified = children[last_mod_idx].text
		modified_by = children[modified_by_idx].text

		contrib = children[contrib_idx].text
		bibcode = children[publish_idx].text
		bibcode = unicodedata.normalize("NFKD",bibcode)
		if contrib == 'Ruiz-Lapuente, et al. 1997, Thermonuclear Supernovae. Dordrecht: Kluwer':
			bibcode = '1997Obs...117..312R'
			contrib = 'Ruiz-Lapuente et al. 1997'
		elif '%26' in bibcode:
			bibcode = bibcode.replace('%26','&')

		SN_dict[SNname][filename] = OrderedDict([
			("Type", SNtype),
			("Redshift", redshift),
			("Obs. Date", obsdate),
			("Program", program),
			("Contributor", contrib),
			("Bibcode", bibcode),
			("Instrument", instrument),
			("Observer", observer),
			("Reduction Status", status),
			("Last Modified", last_modified),
			("Modified By", modified_by)
		]) 

		spectrum_haul[filename] = dat_url
		num_pub_spectra += 1

	if num_private_spectra > 0 and num_pub_spectra !=0:
		print '\tHit', num_private_spectra,'private spectra for', SNname
		with open(_PATH+_DIR_WISEREP+'private-spectra-log.txt', 'a') as f:
			f.write(SNname + ' has ' + str(num_private_spectra) + ' private spectra\n')
			f.close()

	elif num_pub_spectra == 0:
		updateCompletedPickle(SNname,completed)
		savePage(SNname, results_page)
		print '\tAll spectra for', SNname, 'are still private'
		with open(_PATH+_DIR_WISEREP+'private-spectra-log.txt', 'a') as f:
				f.write('All spectra for ' + SNname + ' are still private\n')
				f.close()
		continue

	if len(spectrum_haul) == 1:

		print '\tDownloading 1 public spectrum'

		#make SNname subdirectory
		os.mkdir(_PATH+_DIR_WISEREP+SNname)

		for filename, url in spectrum_haul.items():
			rq = urllib2.Request(url)
			res = urllib2.urlopen(rq)
			dat = open(_PATH+_DIR_WISEREP+SNname+"/"+filename, 'wb')
			dat.write(res.read())
			dat.close()

		#add README for basic metadata to SNname subdirectory
		print '\tWriting README' 

		f = open(_PATH+_DIR_WISEREP+SNname+'/README.txt','wb')
		for file in SN_dict[SNname].keys():
			f.write(file+'\n')
			for key in SN_dict[SNname][file].keys():
				f.write('\t' + '%-*s  %s' % (20, key + ':', SN_dict[SNname][file][key]) + '\n')
		f.close()

		updateCompletedPickle(SNname,completed)
		savePage(SNname, results_page)

	elif len(spectrum_haul) > 1:

		#make SNname subdirectory
		os.mkdir(_PATH+_DIR_WISEREP+SNname)

		for filename, metadata in SN_dict[SNname].items():
			if metadata['Reduction Status'] == 'rapid':
				del SN_dict[SNname][filename]
				del spectrum_haul[filename]

				print '\tRemoving duplicate spectrum for', SNname, '--', filename
				with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
					f.write('Removing duplicate spectrum for ' + SNname + ' -- ' + filename + '\n')
					f.close()

		last_modified = {}
		for k, d in SN_dict[SNname].items():
			for l, e in SN_dict[SNname].items():
				aa = d['Obs. Date'] == e['Obs. Date']
				bb = d['Instrument'] == e['Instrument']
				cc = d['Observer'] == e['Observer']
				dd = d['Modified By'] == 'ofer-UploadSet'
				ee = d['Modified By'] == e['Modified By']
				if aa and bb and cc and dd and ee and k!=l:   #2012fs case
					date = SN_dict[SNname][k]['Last Modified']
					newdate = time.strptime(date, '%Y-%m-%d')
					last_modified[k] = newdate

				elif aa and bb and cc and k!=l:               #2016bau case
					date = SN_dict[SNname][k]['Last Modified']
					newdate = time.strptime(date, '%Y-%m-%d')
					last_modified[k] = newdate


		if len(last_modified) <= 1:
			print '\tPresumably no other duplicate files found for', SNname
			with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
				f.write('Presumably no other duplicate files found for ' + SNname + '\n')
				f.close()

		elif len(last_modified) == 2:
			duplicate = min(last_modified, key=last_modified.get)
			del SN_dict[SNname][duplicate]
			del spectrum_haul[duplicate]

			print '\tRemoving duplicate spectrum for', SNname, '--', duplicate
			with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
				f.write('Removing duplicate spectrum for ' + SNname + ' -- ' + duplicate + '\n')
				f.close()

		count = 1
		for filename, url in spectrum_haul.items():
			print '\tDownloading', count, 'of', len(SN_dict[SNname]), 'public spectra'

			rq = urllib2.Request(url)
			res = urllib2.urlopen(rq)
			dat = open(_PATH+_DIR_WISEREP+SNname+"/"+filename, 'wb')
			dat.write(res.read())
			dat.close()

			count += 1

		#add README for basic metadata to SNname subdirectory
		print '\tWriting README' 

		f = open(_PATH+_DIR_WISEREP+SNname+'/README.txt','wb')
		for file in SN_dict[SNname].keys():
			f.write(file+'\n')
			for key in SN_dict[SNname][file].keys():
				f.write('\t' + '%-*s  %s' % (20, key + ':', SN_dict[SNname][file][key]) + '\n')
		f.close()

		updateCompletedPickle(SNname,completed)
		savePage(SNname, results_page)

#execution time in minutes
minutes = (time.time() - start_time)/60.0
print("Runtime: %s minutes" % minutes)
with open(_PATH+_DIR_WISEREP+'scraper-log.txt', 'a') as f:
			f.write('Runtime: ' + str(minutes) + ' minutes')
			f.close()

