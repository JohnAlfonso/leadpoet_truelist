import requests
import re
import asyncio

from Leadpoet.utils.cloud_db import check_email_duplicate

from email_generation import smart_email_generator
from sn71_truelist_check import check_truelist_email
        
from sn71_db_utils import sn71_update_person_contactinfo, sn71_update_company_contactinfo, is_exist_person_in_db, sn71_db_company_insert_company_with_contactinfo

def check_personemail(person):
    
    full_name = person['fullName']
    companyDomain = person['companyDomain']
    
    # make the workemails
    work_emails = smart_email_generator(full_name, companyDomain, max_results=30)
    work_email = ""
    
    # check duplicate
    for email in work_emails:
        result = check_email_duplicate(email)
        if result:
            return False, "email duplicated"
    
    # check truelist
    for i, email in enumerate(work_emails, 1):
        # print(f"{i:2}. {email}")
        
        # check truelist
        lead = { 'email': email }
        status, result = asyncio.run(check_truelist_email(lead))
        if status == True:
            print (f"   ✔️✔️✔️✔️✔️✔️✔️✔️✔️True")
            work_email = email
            break
        else:
            print (f"   ❌❌❌❌❌❌❌❌❌False")
            pass
    
    if not work_email:
        return False, "workemail truelist check failed"
    
    return True, work_email

def is_valid_full_name(full_name: str) -> bool:
    parts = full_name.strip().split()
    return len(parts) == 2

def check_db_fullname(full_name, companyDomain):
    return

def process_person(person):
    
    # step0: person's base info check
    full_name = person.get("fullName", "")
    if not full_name:
        return False, "Full Name is Empty"
    if not is_valid_full_name(full_name):
        return False, "Full Name is invalid"
    
    linkedin_url = person.get("liVanity", "")
    if not linkedin_url:
        return False, "linkedin_url is Empty"
    
    locality = person.get("locality", "")
    if not locality:
        return False, "locality is Empty"
    
    contactInfo = person.get("contactInfo", {})
    emails = contactInfo.get("emails", [])
    if not emails:
        return False, "contactInfo-emails is []"
    
    companyDomain = person.get("companyDomain", "")
    if not companyDomain:
        return False, "companyDomain is Empty"
    
    ## check the workemail in emails
    # print (companyDomain)
    founded_workemail = False
    for email in emails:
        value = email.get("value", "")
        # print (value)
        if f"@{companyDomain}" in value:
            founded_workemail = True
            break
    if not founded_workemail:
        return False, "workemail is not founded in emails"
    
    # step1: db check
    ## exist in fullname in db ?
    is_exist = is_exist_person_in_db(full_name, companyDomain)
    if is_exist:
        return False, "Person already checked"
    
    # step2: truelist check and duplicate
    # ret, result = check_personemail(person)
    # if ret:
    #     work_email = result
    #     sn71_update_person_contactinfo(person, ret, work_email = work_email)
    #     return True, "OK"
    # else:
    #     reason = result
    #     sn71_update_person_contactinfo(person, ret)
    #     return True, "check email failed"
    sn71_update_person_contactinfo(person)

    return True, "OK"

def process_persons(persons):
    
    if len(persons) == 0:
        return False, "persons's len = 0"
    
    for person in persons:
        ret, reason = process_person(person)
        if ret:
            if reason == 'OK':
                print (f"✅ {person['fullName']} {person['companyDomain']} - person extract success")
            else:
                print (f"❌ {person['fullName']} {person['companyDomain']} - truelist check failed - {reason}")
        else:
            print (f"❌ {person['fullName']} {person['companyDomain']} - person extract failed - {reason}")

def process_company(companyData, add_new=""):
    print(f"Company Data: {companyData}, add_new: {add_new}")
    if not companyData:
        return False
    
    company_contactinfo = {}
    
    linkedin_url = companyData.get("vanity", "")
    print(f"!!!!!!!!!!!!!!!!!!!!! LinkedIn URL: {linkedin_url}, add_new: {add_new}")
    if not linkedin_url:
        return False
    print(f"LinkedIn URL: {linkedin_url}, add_new: {add_new}")
    company_contactinfo['linkedin_url'] = linkedin_url
    
    companyId = companyData.get("companyId", 0)
    if not companyId or companyId == 0:
        return False
    print(f"Company ID: {companyId}, add_new: {add_new}")
    company_contactinfo['companyId'] = companyId

    domain = companyData.get("domain", "")
    if not domain:
        return False
    print(f"Domain: {domain}, add_new: {add_new}")
    company_contactinfo['companyName'] = companyData.get("companyName", "")
    company_contactinfo['description'] = companyData.get("description", "")
    company_contactinfo['website'] = companyData.get("website", "")
    company_contactinfo['domain'] = companyData.get("domain", "")
    company_contactinfo['location'] = companyData.get("location", "")
    company_contactinfo['industry'] = companyData.get("industry", "")
    company_contactinfo['employeesCount'] = companyData.get("employeesCount", "")
    company_contactinfo['companyType'] = companyData.get("companyType", "")
    company_contactinfo['countryCode'] = companyData.get("countryCode", "")
    company_contactinfo['founded'] = companyData.get("founded", "")
    company_contactinfo['source'] = 'contactout'
    if add_new != "":
        if add_new == "exist":
            return False
        elif add_new == "search":
            ret = sn71_db_company_insert_company_with_contactinfo(company_contactinfo, domain)
            return ret
    else:
        print("&&& exist")
        sn71_update_company_contactinfo(company_contactinfo, domain)
    return True

if __name__ == "__main__":
    print (f"{__name__} is called")
    
    # check duplicate and email
    # names = [
    #     "Yolanda Huitron",
    #     "Michelle Davis",
    #     "Troy Billings",
    #     "Travis Faulstich",
    #     "Monika Baker",
    #     "Travis Kerschner",
    #     "Devyn Orchard",
    #     "John Torres",
    #     "Janae Pinch",
    #     "Greg Wilson"
    # ]
    
    # for full_name in names:
    
    #     companyDomain = "printingsolutions.com"
    #     person = {
    #         "full_name": full_name,
    #         "companyDomain": companyDomain
    #     }
    #     ret, workemail = check_personemail(person)
    #     print (ret, workemail)



    # email check
    # lead = {'email': 'travis@printingsolutionsaustin.com'}
    # status, result = asyncio.run(check_truelist_email(lead))
    # print (status, result)