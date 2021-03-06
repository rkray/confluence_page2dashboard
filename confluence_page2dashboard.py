#!/usr/bin/env python3
# author: René Kray <rene@kray.info>
# date: 2017-03-5
#
# check the git repo on githup.com for the latest ersion
# https://github.com/rkray/confluence_page2dashboard
#
# purpose: send reminder emails if confluece pages are out dated

import os
from   pprint   import pprint
from   optparse import OptionParser 
from   datetime import datetime,date
import json
import sys # for eprint needed
import re

# for the usage of mako templates
# http://docs.makotemplates.org/en/latest/
from   mako.template import Template
from   mako.runtime import Context

# Third Party Libraries
# sudo apt install python3-yaml
import yaml
# sudo apt install python3-requests
import requests
# sudo apt install python3-bs4
from   bs4      import BeautifulSoup

# to get the body of a confluence page you have to add
# ?expand=body.storage to the URL
# The body of the page can you find in data["body"]["storage"]["value"]

# little helper function to write error messages to stderr
# usage is similar to the normal print function
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

# Little helper class to handle meta information of confluence pages
class ConfluencePage():
    def __init__(self,base_url,page_id):
        # geting related meta data to page_id
        r = requests.get(base_url+'/'+str(page_id))
        # transform date from json to python dict
        data=dict(json.loads(r.text))

        #pprint(data)

        # setup the propperties
        self.version = data['version']['number']
        self.reviser = data['version']['by']['displayName']
        self.webui   = data['_links']['base']+data['_links']['webui']

        #pprint(self.content)

        last_change = data['version']['when']
        # Confluence Date Format: '2016-09-30T15:06:29.902+02:00'
        # timezone format has to be fixed in the string, because strptime
        # understand the timezone without the colon
        if last_change[-3]==":":
            last_change=last_change[0:-3]+last_change[-2:]

        # parse the date
        self.last_change=datetime.strptime(
            last_change, "%Y-%m-%dT%H:%M:%S.%f%z"
        )

        r = requests.get(base_url+'/'+str(page_id)+'?expand=body.storage')
        data=dict(json.loads(r.text))
        self.title   = data['title']
        self.content = data['body']['storage']['value']
        #pprint(data)


# END of ConfluencePage class

# primary script class
class ConfluencePage2Dashboard():

    ############################################################################
    # setup the Object
    def __init__(self):
        # define defaults here
        self.conf=dict(
            verbose=False,
            configfile = (
                os.environ['HOME']+
                "/."+
                os.path.basename(__file__).replace(".py",".conf")
            )
        )


    ############################################################################
    # Main function
    def run(self):
        self.load_config()

        # get the page related to the page_id
        cpage=ConfluencePage(self.conf['base_url'], int(self.conf['page_id']))
        self.pagetitle=cpage.title

        # extract date from the first table
        table_data=self.parse_html(cpage.content)
        if(self.conf['verbose'] == True):
            pprint(table_data)
        
        # load template from file
        template = Template(
            filename=self.conf['html_template_file'],
        )

        # render the html output
        html = template.render(
            title      = self.pagetitle,
            timestamp  = datetime.now().strftime("%F %T"),
            table_data = table_data
        )

        # write html output to file
        html_file=open(self.conf['html_file'],"w")
        html_file.write(html)
        html_file.close()

        # run the update command
        try:
            self.conf['update_command']
        except:
            if(self.conf['verbose'] == True):
                pprint("no updated command available")
        else:
            os.system(self.conf['update_command'])


    ############################################################################
    # load configuration from file
    def load_config(self):
        try:
            config = yaml.load(open(self.conf['configfile'], 'r'))
        except yaml.scanner.ScannerError as e:
            eprint("There is a problem in your config file!")
            eprint("{}: {}".format(type(e).__name__, e))
            exit(1)
        except FileNotFoundError as e:
            eprint("{}: {}".format(type(e).__name__, e))
            exit(1)

        self.conf.update(config)

        if (self.conf['verbose'] == True):
            pprint(self.conf)


    ############################################################################
    # This function pare all the data from the first table.
    # Expected is a table with headerline and tbody.
    # Table cells must not combined.
    #
    # ToDo:
    # This function is very static and should be rewriten. The column names
    # should be configureable ovver the config file.
    # The function should be renamde to "parse_first_table" or something like
    # that.
    # the functoin is also not very flexible if thee tbody or is missing or if
    # the table has no header line
    def parse_html(self, html_source):
        soup = BeautifulSoup(html_source)
        table = soup.find('table')
        table_body = table.find('tbody')
        rows = table_body.find_all('tr')
        link_pattern=re.compile(
            r'(.*)<ac:link>.*? content-title="(.*?)" .*?</ri:page>(.*)'
        )

        data = []
        for row in rows[1:]:
            cols = row.find_all('td')

            striped_cols=[]
            for td_content in cols:
                #<ac:link><ri:page ri:content-title="bookatiger.com" ri:space-key="hi"></ri:page>

                # remove color parameter like
                # <ac:parameter ac:name="colour">Yellow</ac:parameter>
                [s.extract() for s in td_content('ac:parameter',attrs={"ac:name": "colour"})]

                # Extract the content-title from ri:page element and add this string as
                # text to element. Otherwise the strip function will not regard the text
                for s in td_content('ri:page'):
                    s.string=s['ri:content-title']
                    
                #print(str(td_content))

                text=td_content.text.strip()
                #print(text)
                striped_cols.append(text)

            data.append(dict(
                merchant         = striped_cols[0],
                portal           = striped_cols[1],
                payment_method   = striped_cols[2],
                mi               = striped_cols[3],
                sales            = striped_cols[4],
                est_pv           = striped_cols[5],
                est_go_live_date = striped_cols[6],
                state            = striped_cols[7],
            ))

        return(data)


    ############################################################################
    # evaluate commandline arguments and switches
    def get_arguments(self):
        parser = OptionParser()

        parser.add_option(
            "-c", "--configfile",
            dest    = "configfile",
            default = self.conf['configfile'],
            help    = "read configuration from file")
        parser.add_option(
            "-q", "--quiet",
            action  = "store_false", dest="verbose", default=True,
            help    = "don't print status messages to stdout")

        (options, args) = parser.parse_args()
        # join defaults with optons from command line
        self.conf.update(vars(options))

# END of ConfluenceReminder class

# Run this party only if this file is started as script
if __name__=="__main__":
   cp2d=ConfluencePage2Dashboard()
   cp2d.get_arguments()
   cp2d.run()

