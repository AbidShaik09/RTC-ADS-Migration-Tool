import CONFIG
import UTILS
import sys 
from csv import reader
import csv
import logging
import time
import json
import os
from datetime import datetime
from azure.devops.v5_0.work_item_tracking.models import JsonPatchOperation
from azure.devops.v5_1.work_item_tracking.models import Comment
from azure.devops.v5_1.work_item_tracking.models import CommentCreate
from azure.devops.v5_1.work_item_tracking.models import Wiql
import CREDENTIALS

# Init logging/work_items/json_maps dirs, and create log file
UTILS.init_log_file(CONFIG.logging_filepath +'\\'+CONFIG.logging_filename)  
UTILS.init_dir(CONFIG.work_item_filepath, delete=True)
UTILS.init_dir(CONFIG.json_maps_filepath, delete=False)

# Init migration results csv
timestamp=str(UTILS.current_milli_time())
migration_results_csv_filepath= CONFIG.logging_filepath+'\\'+'migrated_items_'+str(timestamp)+'.csv'
migrated_items_fieldnames = ['RTC ID', 'RTC Type', 'RTC URL', 'ADS ID', 'ADS Type', 'ADS URL', 'WORK ITEM STATUS']
UTILS.create_csv(
    migration_results_csv_filepath, 
    migrated_items_fieldnames
)

# Initialize RTC client connection
try:
    rtc_client, rtc_query_client = UTILS.init_rtc_connection()
except Exception as err:
    UTILS.print_and_log("Error logging into RTC, check your credentials inside CONFIG.py: "+str(err),error=True)
    sys.exit(1)


# Migrate each RTC Query URL
if True:
    for rtc_query_type in CONFIG.rtc_query_urls:
        rtc_query_type_urls = CONFIG.rtc_query_urls[rtc_query_type]
        print("rtc query type urls:")
        print()
        # if rtc query url type has urls
        if len(rtc_query_type_urls) > 0:
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # Query for list of RTC work items
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            # get rtc query properties for this work item type (each property equals a value that rtcclient will query for, more properties==more time, seperating query urls by rtc work itemt ype ensures we dont waste time querying for feature-specific property values when querying epics)
            work_item_properties = None
            try:
                work_item_properties = CONFIG.work_items_property_map[UTILS.format_rtc_type(rtc_query_type)]
            except Exception as e:
                UTILS.print_and_log("Could not find RTC type "+str(UTILS.format_rtc_type(rtc_query_type))+" inside CONFIG.work_items_property_map. Skipping")
            
            if work_item_properties is not None:
                # get rtc common properties (title, description, etc which appear in every work item type)
                common_properties = CONFIG.work_items_property_map['common']
                # combine all property keys into one list (no duplicates)
                properties_list = list(work_item_properties.keys()) + list(common_properties.keys()) + CONFIG.default_rtc_properties
                # run query for rtc work items
                UTILS.print_and_log('running query now')
                query_results = UTILS.query_rtc_urls(rtc_query_type, rtc_query_type_urls, properties_list, rtc_query_client)
                #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                # Migrate each RTC work item in list
                #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                created_work_items_count = 0
                for rtc_work_item in query_results:
                    rtc_id = rtc_work_item.identifier
                    rtc_type = rtc_work_item['type']
                    rtc_url = rtc_work_item['url']
                    UTILS.print_and_log("Migrating " + str(rtc_type) + " RTC ID: " + str(rtc_id) + ". " + str(created_work_items_count) + "/" + str(len(query_results)) )
                    
                    #UTILS.print_and_log("work item does not exists in ads, so migrate it")
                    
                    # try to migrate work item
                    migration_status = UTILS.migrate_work_item(
                        UTILS.format_rtc_type(rtc_work_item.type),
                        rtc_work_item, 
                        migration_results_csv_filepath,
                        rtc_client,
                        ads_wit_client,
                        ads_project,
                        ads_wit_5_1_client
                    )
                    UTILS.print_and_log('migration_status = '+str(migration_status))

                    # migrate work item parent 
                    if CONFIG.migrate_parent is True:
                        try:
                            rtc_parent = rtc_work_item.getParent()
                            # if parent exists, and has not been migrated, migrate it
                            if rtc_parent is not None:
                                # try to migrate parent
                                migration_status = UTILS.migrate_work_item(
                                    UTILS.format_rtc_type(rtc_parent.type),
                                    rtc_parent, 
                                    migration_results_csv_filepath,
                                    rtc_client,
                                    ads_wit_client,
                                    ads_project,
                                    ads_wit_5_1_client
                                )
                                UTILS.print_and_log('migrated parent')
                        except Exception as e:
                            UTILS.print_and_log("Error getting work item parent: "+str(e)+'\n',error=True)

                    
                    # migrate work item children
                    if CONFIG.migrate_children is True:
                        try:
                            rtc_children = rtc_work_item.getChildren()
                            # if children were found
                            if rtc_children is not None:
                                # for each child
                                child_num = 0
                                for rtc_child in rtc_children:
                                    rtc_child_id=rtc_child.identifier
                                    UTILS.print_and_log('examining child rtc id: ' + str(rtc_child_id) + ', ' + str(child_num) + "/" + str(len(rtc_children)))
                                    # try to migrate  
                                    migration_status = UTILS.migrate_work_item(
                                        UTILS.format_rtc_type(rtc_child.type),
                                        rtc_child, 
                                        migration_results_csv_filepath,
                                        rtc_client,
                                        ads_wit_client,
                                        ads_project,
                                        ads_wit_5_1_client
                                    )
                                    child_num=child_num+1

                                    # migrate children of children
                                    if CONFIG.migrate_children_of_children is True:
                                        rtc_more_children = rtc_child.getChildren()
                                        more_child_num = 0
                                        for rtc_more_child in rtc_more_children:
                                            UTILS.print_and_log('examining child or child. id=' + str(rtc_more_child.identifier) + ', ' + str(more_child_num) + "/" + str(len(rtc_more_children)))
                                            # try to migrate  
                                            migration_status = UTILS.migrate_work_item(
                                                UTILS.format_rtc_type(rtc_more_child.type),
                                                rtc_more_child, 
                                                migration_results_csv_filepath,
                                                rtc_client,
                                                ads_wit_client,
                                                ads_project,
                                                ads_wit_5_1_client
                                            )
                        except Exception as e:
                            UTILS.print_and_log("Error getting work item children: "+str(e)+'\n',error=True)

