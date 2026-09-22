from datetime import datetime
import csv
from collections import defaultdict

deceased = defaultdict(lambda: {"Account Id": "", "Account Name": "", "Legal Entity": "", "Land Holding Type": "", "Total Gross Acreage": "", "County": "", "Entity Type": "", "Mineral Owner Royalty": "", "Title Source": "", "Title Landman": "", "Section Name": "", "Section Id": "", "Section": "", "Township": "", "Township Name": "", "Range": "", "State": "", "Tract Description": "", "Title Information": "", "Title Certification Date": "", "Signer 1": "", "Signer 1 Capacity": "", "Signer 1 Last Name": "", "Mineral Interest": 0, "Quarter Section": "", "NENE NMA": 0, "NWNE NMA": 0, "SWNE NMA": 0, "SENE NMA": 0, "NENW NMA": 0, "NWNW NMA": 0, "SWNW NMA": 0, "SENW NMA": 0, "NESW NMA": 0, "NWSW NMA": 0, "SWSW NMA": 0, "SESW NMA": 0, "NESE NMA": 0, "NWSE NMA": 0, "SWSE NMA": 0, "SESE NMA": 0, "Lease Royalty": 0, "Lease Notes & Additional Documentation": "", "$/Acre for Extension": "", "Agreement Effective Date": "", "Agreement Executed Date": "", "Area of Interest": "", "Abstract": "", "Accumulated Depletion": "", "Accumulated Impairment": "", "Accumulated Intangible Capex": "", "Accumulated Tangible Capex": "", "Additional Lands": "", "Additional NMA Justification": "", "Approximate Additional NMA": "", "As of Date Funds Collected": "", "Asset Conveyance": "", "Assignment Effective Date": "", "Assignment Executed Date": "", "Assignment Record ID": "", "Assignment Transferee": "", "Assignment Transferor": "", "Audited By": "", "Audited By Id": "", "Base OGL": "", "Basis Exchanged": "", "Basis Transferred": "", "Basis Written Off": "", "Block": "", "C.O.P.": "", "Category Factor": "", "Close Date": "", "Comments": "", "Consent to Assign Req?": "", "DSU Comments": "", "DSU ID #": "", "DSU Name": "", "Data Req?": "", "Date Election Delivered": "", "Date Election Sent": "", "Date of Election Expiration": "", "Deal Number": "", "Depths Included Leasehold": "", "Depths Included Mineral Estate": "", "Division Order Sent": "", "Document Effective Date": "", "Document Recording #": "", "Document Recording Date": "", "Elect to Participate?": "", "Election Certified Mail Tracking Number": "", "Extension Expiration": "", "Federal Lease?": "", "Finance Notes": "", "Force Pooled?": "", "Force Update?": "", "Funds Collected": "", "Funds to be Collected?": "", "HBP": "", "Holding Letter": "", "LH Priority": "", "Lease Extension Filed": "", "Leasehold Depth Severance?": "", "Legal Description [1]": "", "Legal Description [2]": "", "Legal Description [3]": "", "Legal Description [4]": "", "Marketable?": "", "Mineral Depth Severance?": "", "Mortgage Document ID": "", "Mortgage Effective Date": "", "Mortgage Executed Date": "", "Mortgagee": "", "Mortgagor": "", "NMA Sold": "", "Next Finance Follow-Up": "", "Non-consent Penalty": "", "OGL Auditor": "", "OGL Effective Date": "", "Operating Notes": "", "Operator": "", "Optional Extension": "", "Original $/Acre Bonus": "", "Original Lessee": "", "PHX Operated DSU?": "", "PPC Exempt": "", "PPC Language": "", "Phoenix in Pay?": "", "Primary Term": "", "Primary Term Expiration": "", "Production Effective Date": "", "Pugh Clause": "", "Purchasing Party": "", "Quarter/Quarter": "", "Ready for Mailer?": "", "Reporting Area": "", "Royalties for Flared Gas": "", "Sale Effective Date": "", "Sale Executed Date": "", "Shut-In (time/$)": "", "Signer 2": "", "Signer 2 Capacity": "", "Signer 2 Last Name": "", "Signer 3": "", "Signer 3 Capacity": "", "Signer 4": "", "Signer 5": "", "Signer 6": "", "Signer 7": "", "Signer 8": "", "Signer 9": "", "Sold Before?": "", "Spacing Unit Acreage Est.": "", "State Lease?": "", "Survey (Full Name)": "", "Survey": "", "Suspense Requested?": "", "Title Requirement": "", "Total Cost to Extend": 0, "Township Id": "", "Transaction Broker": "", "Tribal Lease?": "", "Unique OGL Id": "", "Year of Acquisition": ""})
heirs = defaultdict(lambda: {"Account Id": "", "Account Name": "", "Legal Entity": "", "Land Holding Type": "", "Total Gross Acreage": "", "County": "", "Entity Type": "", "Mineral Owner Royalty": "", "Title Source": "", "Title Landman": "", "Section Name": "", "Section Id": "", "Section": "", "Township": "", "Township Name": "", "Range": "", "State": "", "Tract Description": "", "Title Information": "", "Title Certification Date": "", "Signer 1": "", "Signer 1 Capacity": "", "Signer 1 Last Name": "", "Mineral Interest": 0, "Quarter Section": "", "NENE NMA": 0, "NWNE NMA": 0, "SWNE NMA": 0, "SENE NMA": 0, "NENW NMA": 0, "NWNW NMA": 0, "SWNW NMA": 0, "SENW NMA": 0, "NESW NMA": 0, "NWSW NMA": 0, "SWSW NMA": 0, "SESW NMA": 0, "NESE NMA": 0, "NWSE NMA": 0, "SWSE NMA": 0, "SESE NMA": 0, "Lease Royalty": 0, "Lease Notes & Additional Documentation": "", "$/Acre for Extension": "", "Agreement Effective Date": "", "Agreement Executed Date": "", "Area of Interest": "", "Abstract": "", "Accumulated Depletion": "", "Accumulated Impairment": "", "Accumulated Intangible Capex": "", "Accumulated Tangible Capex": "", "Additional Lands": "", "Additional NMA Justification": "", "Approximate Additional NMA": "", "As of Date Funds Collected": "", "Asset Conveyance": "", "Assignment Effective Date": "", "Assignment Executed Date": "", "Assignment Record ID": "", "Assignment Transferee": "", "Assignment Transferor": "", "Audited By": "", "Audited By Id": "", "Base OGL": "", "Basis Exchanged": "", "Basis Transferred": "", "Basis Written Off": "", "Block": "", "C.O.P.": "", "Category Factor": "", "Close Date": "", "Comments": "", "Consent to Assign Req?": "", "DSU Comments": "", "DSU ID #": "", "DSU Name": "", "Data Req?": "", "Date Election Delivered": "", "Date Election Sent": "", "Date of Election Expiration": "", "Deal Number": "", "Depths Included Leasehold": "", "Depths Included Mineral Estate": "", "Division Order Sent": "", "Document Effective Date": "", "Document Recording #": "", "Document Recording Date": "", "Elect to Participate?": "", "Election Certified Mail Tracking Number": "", "Extension Expiration": "", "Federal Lease?": "", "Finance Notes": "", "Force Pooled?": "", "Force Update?": "", "Funds Collected": "", "Funds to be Collected?": "", "HBP": "", "Holding Letter": "", "LH Priority": "", "Lease Extension Filed": "", "Leasehold Depth Severance?": "", "Legal Description [1]": "", "Legal Description [2]": "", "Legal Description [3]": "", "Legal Description [4]": "", "Marketable?": "", "Mineral Depth Severance?": "", "Mortgage Document ID": "", "Mortgage Effective Date": "", "Mortgage Executed Date": "", "Mortgagee": "", "Mortgagor": "", "NMA Sold": "", "Next Finance Follow-Up": "", "Non-consent Penalty": "", "OGL Auditor": "", "OGL Effective Date": "", "Operating Notes": "", "Operator": "", "Optional Extension": "", "Original $/Acre Bonus": "", "Original Lessee": "", "PHX Operated DSU?": "", "PPC Exempt": "", "PPC Language": "", "Phoenix in Pay?": "", "Primary Term": "", "Primary Term Expiration": "", "Production Effective Date": "", "Pugh Clause": "", "Purchasing Party": "", "Quarter/Quarter": "", "Ready for Mailer?": "", "Reporting Area": "", "Royalties for Flared Gas": "", "Sale Effective Date": "", "Sale Executed Date": "", "Shut-In (time/$)": "", "Signer 2": "", "Signer 2 Capacity": "", "Signer 2 Last Name": "", "Signer 3": "", "Signer 3 Capacity": "", "Signer 4": "", "Signer 5": "", "Signer 6": "", "Signer 7": "", "Signer 8": "", "Signer 9": "", "Sold Before?": "", "Spacing Unit Acreage Est.": "", "State Lease?": "", "Survey (Full Name)": "", "Survey": "", "Suspense Requested?": "", "Title Requirement": "", "Total Cost to Extend": 0, "Township Id": "", "Transaction Broker": "", "Tribal Lease?": "", "Unique OGL Id": "", "Year of Acquisition": ""})
user_heirs = defaultdict(lambda: {"legal entity": "", "percentage ownership": 1, "Account Id": "", "Account Name": "", "Entity Type": "", "Signer 1": "", "Signer 1 Capacity": "", "Signer 1 Last Name": "", "Signer 2": "", "Signer 2 Capacity": "", "Signer 2 Last Name": "", "Signer 3": "", "Signer 3 Capacity": "", "Signer 4": "", "Signer 5": "", "Signer 6": "", "Signer 7": "", "Signer 8": "", "Signer 9": "", "Title Info": ""}) # Going to need a way for users to enter this

deceased_path = r"C:\Users\Ethan Mesecher\Desktop\Bring out your dead\EM_Deceased_Account_Distribution_(LH).csv"
heir_csv_path = r"C:\Users\Ethan Mesecher\Desktop\Bring out your dead\heir_template.csv"
output_csv_path = r"C:\Users\Ethan Mesecher\Desktop\Bring out your dead\deceased_upload.csv"

with open(heir_csv_path, "r", encoding="utf-8-sig") as file: # Opens deceased account and gets all the information from it
    csv_reader = csv.reader(file)
    for i, row in enumerate(csv_reader):
        if i == 0:
            continue  # Skip the header row

        legal_entity = row[3]
        user_heirs[legal_entity]["percentage ownership"] = row[0]
        user_heirs[legal_entity]["Account Id"] = row[1]
        user_heirs[legal_entity]["Account Name"] = row[2]
        user_heirs[legal_entity]["legal entity"] = row[3]
        user_heirs[legal_entity]["Entity Type"] = row[4]
        user_heirs[legal_entity]["Signer 1"] = row[5]
        user_heirs[legal_entity]["Signer 1 Capacity"] = row[6]
        user_heirs[legal_entity]["Signer 1 Last Name"] = row[7]
        user_heirs[legal_entity]["Signer 2"] = row[8]
        user_heirs[legal_entity]["Signer 2 Capacity"] = row[9]
        user_heirs[legal_entity]["Signer 2 Last Name"] = row[10]
        user_heirs[legal_entity]["Signer 3"] = row[11]
        user_heirs[legal_entity]["Signer 3 Capacity"] = row[12]
        user_heirs[legal_entity]["Signer 4"] = row[13]
        user_heirs[legal_entity]["Signer 5"] = row[14]
        user_heirs[legal_entity]["Signer 6"] = row[15]
        user_heirs[legal_entity]["Signer 7"] = row[16]
        user_heirs[legal_entity]["Signer 8"] = row[17]
        user_heirs[legal_entity]["Signer 9"] = row[18]
        user_heirs[legal_entity]["title information"] = row[19]


with open(deceased_path, "r", encoding="utf-8-sig") as file: # Opens deceased account and gets all the information from it
    csv_reader = csv.reader(file)
    for i, row in enumerate(csv_reader):
        if i == 0:
            continue  # Skip the header row

        legal_entity = row[2]+row[10] #Legal entity here isn't just LE, it's also the STR to let it create multiple holdings with the same LE, this is not the same as the value in Legal Entity, it's confusing but would be annoying to fix
        #print (legal_entity)

        deceased[legal_entity]["Account Id"] = row[0]
        deceased[legal_entity]["Account Name"] = row[1]
        deceased[legal_entity]["Legal Entity"] = row[2]
        deceased[legal_entity]["Land Holding Type"] = row[3]
        deceased[legal_entity]["Total Gross Acreage"] = row[4]
        deceased[legal_entity]["County"] = row[5]
        deceased[legal_entity]["Entity Type"] = row[6]
        deceased[legal_entity]["Mineral Owner Royalty"] = row[7]
        deceased[legal_entity]["Title Source"] = row[8]
        deceased[legal_entity]["Title Landman"] = row[9]
        deceased[legal_entity]["Section Name"] = row[10]
        deceased[legal_entity]["Section Id"] = row[11]
        deceased[legal_entity]["Section"] = row[12]
        deceased[legal_entity]["Township"] = row[13]
        deceased[legal_entity]["Township Name"] = row[14]
        deceased[legal_entity]["Range"] = row[15]
        deceased[legal_entity]["State"] = row[16]
        deceased[legal_entity]["Tract Description"] = row[17]
        deceased[legal_entity]["Title Information"] = row[18]
        deceased[legal_entity]["Title Certification Date"] = row[19]
        deceased[legal_entity]["Signer 1"] = row[20]
        deceased[legal_entity]["Signer 1 Capacity"] = row[21]
        deceased[legal_entity]["Signer 1 Last Name"] = row[22]
        deceased[legal_entity]["Mineral Interest"] = row[23]
        deceased[legal_entity]["Quarter Section"] = row[24]
        deceased[legal_entity]["NENE NMA"] = row[25]
        deceased[legal_entity]["NWNE NMA"] = row[26]
        deceased[legal_entity]["SWNE NMA"] = row[27]
        deceased[legal_entity]["SENE NMA"] = row[28]
        deceased[legal_entity]["NENW NMA"] = row[29]
        deceased[legal_entity]["NWNW NMA"] = row[30]
        deceased[legal_entity]["SWNW NMA"] = row[31]
        deceased[legal_entity]["SENW NMA"] = row[32]
        deceased[legal_entity]["NESW NMA"] = row[33]
        deceased[legal_entity]["NWSW NMA"] = row[34]
        deceased[legal_entity]["SWSW NMA"] = row[35]
        deceased[legal_entity]["SESW NMA"] = row[36]
        deceased[legal_entity]["NESE NMA"] = row[37]
        deceased[legal_entity]["NWSE NMA"] = row[38]
        deceased[legal_entity]["SWSE NMA"] = row[39]
        deceased[legal_entity]["SESE NMA"] = row[40]
        deceased[legal_entity]["Lease Royalty"] = row[41]
        deceased[legal_entity]["Lease Notes & Additional Documentation"] = row[42]
        deceased[legal_entity]["$/Acre for Extension"] = row[43]
        deceased[legal_entity]["Agreement Effective Date"] = row[44]
        deceased[legal_entity]["Agreement Executed Date"] = row[45]
        deceased[legal_entity]["Area of Interest"] = row[46]
        deceased[legal_entity]["Abstract"] = row[47]
        deceased[legal_entity]["Accumulated Depletion"] = row[48]
        deceased[legal_entity]["Accumulated Impairment"] = row[49]
        deceased[legal_entity]["Accumulated Intangible Capex"] = row[50]
        deceased[legal_entity]["Accumulated Tangible Capex"] = row[51]
        deceased[legal_entity]["Additional Lands"] = row[52]
        deceased[legal_entity]["Additional NMA Justification"] = row[53]
        deceased[legal_entity]["Approximate Additional NMA"] = row[54]
        deceased[legal_entity]["As of Date Funds Collected"] = row[55]
        deceased[legal_entity]["Asset Conveyance"] = row[56]
        deceased[legal_entity]["Assignment Effective Date"] = row[57]
        deceased[legal_entity]["Assignment Executed Date"] = row[58]
        deceased[legal_entity]["Assignment Record ID"] = row[59]
        deceased[legal_entity]["Assignment Transferee"] = row[60]
        deceased[legal_entity]["Assignment Transferor"] = row[61]
        deceased[legal_entity]["Audited By"] = row[62]
        deceased[legal_entity]["Audited By Id"] = row[63]
        deceased[legal_entity]["Base OGL"] = row[64]
        deceased[legal_entity]["Basis Exchanged"] = row[65]
        deceased[legal_entity]["Basis Transferred"] = row[66]
        deceased[legal_entity]["Basis Written Off"] = row[67]
        deceased[legal_entity]["Block"] = row[68]
        deceased[legal_entity]["C.O.P."] = row[69]
        deceased[legal_entity]["Category Factor"] = row[70]
        deceased[legal_entity]["Close Date"] = row[71]
        deceased[legal_entity]["Comments"] = row[72]
        deceased[legal_entity]["Consent to Assign Req?"] = row[73]
        deceased[legal_entity]["DSU Comments"] = row[74]
        deceased[legal_entity]["DSU ID #"] = row[75]
        deceased[legal_entity]["DSU Name"] = row[76]
        deceased[legal_entity]["Data Req?"] = row[77]
        deceased[legal_entity]["Date Election Delivered"] = row[78]
        deceased[legal_entity]["Date Election Sent"] = row[79]
        deceased[legal_entity]["Date of Election Expiration"] = row[80]
        deceased[legal_entity]["Deal Number"] = row[81]
        deceased[legal_entity]["Depths Included Leasehold"] = row[82]
        deceased[legal_entity]["Depths Included Mineral Estate"] = row[83]
        deceased[legal_entity]["Division Order Sent"] = row[84]
        deceased[legal_entity]["Document Effective Date"] = row[85]
        deceased[legal_entity]["Document Recording #"] = row[86]
        deceased[legal_entity]["Document Recording Date"] = row[87]
        deceased[legal_entity]["Elect to Participate?"] = row[88]
        deceased[legal_entity]["Election Certified Mail Tracking Number"] = row[89]
        deceased[legal_entity]["Extension Expiration"] = row[90]
        deceased[legal_entity]["Federal Lease?"] = row[91]
        deceased[legal_entity]["Finance Notes"] = row[92]
        deceased[legal_entity]["Force Pooled?"] = row[93]
        deceased[legal_entity]["Force Update?"] = row[94]
        deceased[legal_entity]["Funds Collected"] = row[95]
        deceased[legal_entity]["Funds to be Collected?"] = row[96]
        deceased[legal_entity]["HBP"] = row[97]
        deceased[legal_entity]["Holding Letter"] = row[98]
        deceased[legal_entity]["LH Priority"] = row[99]
        deceased[legal_entity]["Lease Extension Filed"] = row[100]
        deceased[legal_entity]["Leasehold Depth Severance?"] = row[101]
        deceased[legal_entity]["Legal Description [1]"] = row[102]
        deceased[legal_entity]["Legal Description [2]"] = row[103]
        deceased[legal_entity]["Legal Description [3]"] = row[104]
        deceased[legal_entity]["Legal Description [4]"] = row[105]
        deceased[legal_entity]["Marketable?"] = row[106]
        deceased[legal_entity]["Mineral Depth Severance?"] = row[107]
        deceased[legal_entity]["Mortgage Document ID"] = row[108]
        deceased[legal_entity]["Mortgage Effective Date"] = row[109]
        deceased[legal_entity]["Mortgage Executed Date"] = row[110]
        deceased[legal_entity]["Mortgagee"] = row[111]
        deceased[legal_entity]["Mortgagor"] = row[112]
        deceased[legal_entity]["NMA Sold"] = row[113]
        deceased[legal_entity]["Next Finance Follow-Up"] = row[114]
        deceased[legal_entity]["Non-consent Penalty"] = row[115]
        deceased[legal_entity]["OGL Auditor"] = row[116]
        deceased[legal_entity]["OGL Effective Date"] = row[117]
        deceased[legal_entity]["Operating Notes"] = row[118]
        deceased[legal_entity]["Operator"] = row[119]
        deceased[legal_entity]["Optional Extension"] = row[120]
        deceased[legal_entity]["Original $/Acre Bonus"] = row[121]
        deceased[legal_entity]["Original Lessee"] = row[122]
        deceased[legal_entity]["PHX Operated DSU?"] = row[123]
        deceased[legal_entity]["PPC Exempt"] = row[124]
        deceased[legal_entity]["PPC Language"] = row[125]
        deceased[legal_entity]["Phoenix in Pay?"] = row[126]
        deceased[legal_entity]["Primary Term"] = row[127]
        deceased[legal_entity]["Primary Term Expiration"] = row[128]
        deceased[legal_entity]["Production Effective Date"] = row[129]
        deceased[legal_entity]["Pugh Clause"] = row[130]
        deceased[legal_entity]["Purchasing Party"] = row[131]
        deceased[legal_entity]["Quarter/Quarter"] = row[132]
        deceased[legal_entity]["Ready for Mailer?"] = row[133]
        deceased[legal_entity]["Reporting Area"] = row[134]
        deceased[legal_entity]["Royalties for Flared Gas"] = row[135]
        deceased[legal_entity]["Sale Effective Date"] = row[136]
        deceased[legal_entity]["Sale Executed Date"] = row[137]
        deceased[legal_entity]["Shut-In (time/$)"] = row[138]
        deceased[legal_entity]["Signer 2"] = row[139]
        deceased[legal_entity]["Signer 2 Capacity"] = row[140]
        deceased[legal_entity]["Signer 2 Last Name"] = row[141]
        deceased[legal_entity]["Signer 3"] = row[142]
        deceased[legal_entity]["Signer 3 Capacity"] = row[143]
        deceased[legal_entity]["Signer 4"] = row[144]
        deceased[legal_entity]["Signer 5"] = row[145]
        deceased[legal_entity]["Signer 6"] = row[146]
        deceased[legal_entity]["Signer 7"] = row[147]
        deceased[legal_entity]["Signer 8"] = row[148]
        deceased[legal_entity]["Signer 9"] = row[149]
        deceased[legal_entity]["Sold Before?"] = row[150]
        deceased[legal_entity]["Spacing Unit Acreage Est."] = row[151]
        deceased[legal_entity]["State Lease?"] = row[152]
        deceased[legal_entity]["Survey (Full Name)"] = row[153]
        deceased[legal_entity]["Survey"] = row[154]
        deceased[legal_entity]["Suspense Requested?"] = row[155]
        deceased[legal_entity]["Title Requirement"] = row[156]
        deceased[legal_entity]["Total Cost to Extend"] = row[157]
        deceased[legal_entity]["Township Id"] = row[158]
        deceased[legal_entity]["Transaction Broker"] = row[159]
        deceased[legal_entity]["Tribal Lease?"] = row[160]
        deceased[legal_entity]["Unique OGL Id"] = row[161]
        deceased[legal_entity]["Year of Acquisition"] = row[162]

for user_heir in user_heirs:
    for id in deceased:
        heir_id = user_heirs[user_heir]["legal entity"]+deceased[id]["Section Name"]+deceased[id]["Land Holding Type"]+deceased[id]["Title Source"]+deceased[id]["Legal Entity"]
        heirs[heir_id]["Account Id"] = user_heirs[user_heir]["Account Id"]
        heirs[heir_id]["Account Name"] = user_heirs[user_heir]["Account Name"]
        heirs[heir_id]["Legal Entity"] = user_heirs[user_heir]["legal entity"]
        heirs[heir_id]["Land Holding Type"] = deceased[id]["Land Holding Type"]
        heirs[heir_id]["Total Gross Acreage"] = deceased[id]["Total Gross Acreage"]
        heirs[heir_id]["County"] = deceased[id]["County"]
        heirs[heir_id]["Entity Type"] = user_heirs[user_heir]["Entity Type"]
        heirs[heir_id]["Mineral Owner Royalty"] = deceased[id]["Mineral Owner Royalty"]
        heirs[heir_id]["Title Source"] = deceased[id]["Title Source"]
        heirs[heir_id]["Title Landman"] = "EM"
        heirs[heir_id]["Section Name"] = deceased[id]["Section Name"]
        heirs[heir_id]["Section Id"] = deceased[id]["Section Id"]
        heirs[heir_id]["Section"] = deceased[id]["Section"]
        heirs[heir_id]["Township"] = deceased[id]["Township"]
        heirs[heir_id]["Township Name"] = deceased[id]["Township Name"]
        heirs[heir_id]["Range"] = deceased[id]["Range"]
        heirs[heir_id]["State"] = deceased[id]["State"]
        heirs[heir_id]["Tract Description"] = deceased[id]["Tract Description"]

        Title = (
            "\n\nThis was created as part of a distribution as heir to "
            f"{deceased[id]['Account Name']}.\n\n"
        )

        heirs[heir_id]["Title Information"] = user_heirs[user_heir]["title information"]+Title+deceased[id]["Title Information"]
        today_str = datetime.today().strftime("%m/%d/%Y")
        heirs[heir_id]["Title Certification Date"] = today_str
        heirs[heir_id]["Signer 1"] = user_heirs[user_heir]["Signer 1"]
        heirs[heir_id]["Signer 1 Capacity"] = user_heirs[user_heir]["Signer 1 Capacity"]
        heirs[heir_id]["Signer 1 Last Name"] = user_heirs[user_heir]["Signer 1 Last Name"]
        heirs[heir_id]["Mineral Interest"] = float(deceased[id]["Mineral Interest"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["Quarter Section"] = deceased[id]["Quarter Section"]
        heirs[heir_id]["NENE NMA"] = float(deceased[id]["NENE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NWNE NMA"] = float(deceased[id]["NWNE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SWNE NMA"] = float(deceased[id]["SWNE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SENE NMA"] = float(deceased[id]["SENE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NENW NMA"] = float(deceased[id]["NENW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NWNW NMA"] = float(deceased[id]["NWNW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SWNW NMA"] = float(deceased[id]["SWNW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SENW NMA"] = float(deceased[id]["SENW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NESW NMA"] = float(deceased[id]["NESW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NWSW NMA"] = float(deceased[id]["NWSW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SWSW NMA"] = float(deceased[id]["SWSW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SESW NMA"] = float(deceased[id]["SESW NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NESE NMA"] = float(deceased[id]["NESE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["NWSE NMA"] = float(deceased[id]["NWSE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SWSE NMA"] = float(deceased[id]["SWSE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["SESE NMA"] = float(deceased[id]["SESE NMA"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["Lease Royalty"] = deceased[id]["Lease Royalty"]
        heirs[heir_id]["Lease Notes & Additional Documentation"] = deceased[id]["Lease Notes & Additional Documentation"]
        heirs[heir_id]["$/Acre for Extension"] = deceased[id]["$/Acre for Extension"]
        heirs[heir_id]["Agreement Effective Date"] = deceased[id]["Agreement Effective Date"]
        heirs[heir_id]["Agreement Executed Date"] = deceased[id]["Agreement Executed Date"]
        heirs[heir_id]["Area of Interest"] = deceased[id]["Area of Interest"]
        heirs[heir_id]["Abstract"] = deceased[id]["Abstract"]
        heirs[heir_id]["Accumulated Depletion"] = deceased[id]["Accumulated Depletion"]
        heirs[heir_id]["Accumulated Impairment"] = deceased[id]["Accumulated Impairment"]
        heirs[heir_id]["Accumulated Intangible Capex"] = deceased[id]["Accumulated Intangible Capex"]
        heirs[heir_id]["Accumulated Tangible Capex"] = deceased[id]["Accumulated Tangible Capex"]
        heirs[heir_id]["Additional Lands"] = deceased[id]["Additional Lands"]
        heirs[heir_id]["Additional NMA Justification"] = deceased[id]["Additional NMA Justification"]
        heirs[heir_id]["Approximate Additional NMA"] = deceased[id]["Approximate Additional NMA"]
        heirs[heir_id]["As of Date Funds Collected"] = deceased[id]["As of Date Funds Collected"]
        heirs[heir_id]["Asset Conveyance"] = deceased[id]["Asset Conveyance"]
        heirs[heir_id]["Assignment Effective Date"] = deceased[id]["Assignment Effective Date"]
        heirs[heir_id]["Assignment Executed Date"] = deceased[id]["Assignment Executed Date"]
        heirs[heir_id]["Assignment Record ID"] = deceased[id]["Assignment Record ID"]
        heirs[heir_id]["Assignment Transferee"] = deceased[id]["Assignment Transferee"]
        heirs[heir_id]["Assignment Transferor"] = deceased[id]["Assignment Transferor"]
        heirs[heir_id]["Audited By"] = deceased[id]["Audited By"]
        heirs[heir_id]["Audited By Id"] = deceased[id]["Audited By Id"]
        heirs[heir_id]["Base OGL"] = deceased[id]["Base OGL"]
        heirs[heir_id]["Basis Exchanged"] = deceased[id]["Basis Exchanged"]
        heirs[heir_id]["Basis Transferred"] = deceased[id]["Basis Transferred"]
        heirs[heir_id]["Basis Written Off"] = deceased[id]["Basis Written Off"]
        heirs[heir_id]["Block"] = deceased[id]["Block"]
        heirs[heir_id]["C.O.P."] = deceased[id]["C.O.P."]
        heirs[heir_id]["Category Factor"] = deceased[id]["Category Factor"]
        heirs[heir_id]["Close Date"] = deceased[id]["Close Date"]
        heirs[heir_id]["Comments"] = deceased[id]["Comments"]
        heirs[heir_id]["Consent to Assign Req?"] = deceased[id]["Consent to Assign Req?"]
        heirs[heir_id]["DSU Comments"] = deceased[id]["DSU Comments"]
        heirs[heir_id]["DSU ID #"] = deceased[id]["DSU ID #"]
        heirs[heir_id]["DSU Name"] = deceased[id]["DSU Name"]
        heirs[heir_id]["Data Req?"] = deceased[id]["Data Req?"]
        heirs[heir_id]["Date Election Delivered"] = deceased[id]["Date Election Delivered"]
        heirs[heir_id]["Date Election Sent"] = deceased[id]["Date Election Sent"]
        heirs[heir_id]["Date of Election Expiration"] = deceased[id]["Date of Election Expiration"]
        heirs[heir_id]["Deal Number"] = deceased[id]["Deal Number"]
        heirs[heir_id]["Depths Included Leasehold"] = deceased[id]["Depths Included Leasehold"]
        heirs[heir_id]["Depths Included Mineral Estate"] = deceased[id]["Depths Included Mineral Estate"]
        heirs[heir_id]["Division Order Sent"] = deceased[id]["Division Order Sent"]
        heirs[heir_id]["Document Effective Date"] = deceased[id]["Document Effective Date"]
        heirs[heir_id]["Document Recording #"] = deceased[id]["Document Recording #"]
        heirs[heir_id]["Document Recording Date"] = deceased[id]["Document Recording Date"]
        heirs[heir_id]["Elect to Participate?"] = deceased[id]["Elect to Participate?"]
        heirs[heir_id]["Election Certified Mail Tracking Number"] = deceased[id]["Election Certified Mail Tracking Number"]
        heirs[heir_id]["Extension Expiration"] = deceased[id]["Extension Expiration"]
        heirs[heir_id]["Federal Lease?"] = deceased[id]["Federal Lease?"]
        heirs[heir_id]["Finance Notes"] = deceased[id]["Finance Notes"]
        heirs[heir_id]["Force Pooled?"] = deceased[id]["Force Pooled?"]
        heirs[heir_id]["Force Update?"] = deceased[id]["Force Update?"]
        heirs[heir_id]["Funds Collected"] = deceased[id]["Funds Collected"]
        heirs[heir_id]["Funds to be Collected?"] = deceased[id]["Funds to be Collected?"]
        heirs[heir_id]["HBP"] = deceased[id]["HBP"]
        heirs[heir_id]["Holding Letter"] = deceased[id]["Holding Letter"]
        heirs[heir_id]["LH Priority"] = deceased[id]["LH Priority"]
        heirs[heir_id]["Lease Extension Filed"] = deceased[id]["Lease Extension Filed"]
        heirs[heir_id]["Leasehold Depth Severance?"] = deceased[id]["Leasehold Depth Severance?"]
        heirs[heir_id]["Legal Description [1]"] = deceased[id]["Legal Description [1]"]
        heirs[heir_id]["Legal Description [2]"] = deceased[id]["Legal Description [2]"]
        heirs[heir_id]["Legal Description [3]"] = deceased[id]["Legal Description [3]"]
        heirs[heir_id]["Legal Description [4]"] = deceased[id]["Legal Description [4]"]
        heirs[heir_id]["Marketable?"] = deceased[id]["Marketable?"]
        heirs[heir_id]["Mineral Depth Severance?"] = deceased[id]["Mineral Depth Severance?"]
        heirs[heir_id]["Mortgage Document ID"] = deceased[id]["Mortgage Document ID"]
        heirs[heir_id]["Mortgage Effective Date"] = deceased[id]["Mortgage Effective Date"]
        heirs[heir_id]["Mortgage Executed Date"] = deceased[id]["Mortgage Executed Date"]
        heirs[heir_id]["Mortgagee"] = deceased[id]["Mortgagee"]
        heirs[heir_id]["Mortgagor"] = deceased[id]["Mortgagor"]
        heirs[heir_id]["NMA Sold"] = deceased[id]["NMA Sold"]
        heirs[heir_id]["Next Finance Follow-Up"] = deceased[id]["Next Finance Follow-Up"]
        heirs[heir_id]["Non-consent Penalty"] = deceased[id]["Non-consent Penalty"]
        heirs[heir_id]["OGL Auditor"] = deceased[id]["OGL Auditor"]
        heirs[heir_id]["OGL Effective Date"] = deceased[id]["OGL Effective Date"]
        heirs[heir_id]["Operating Notes"] = deceased[id]["Operating Notes"]
        heirs[heir_id]["Operator"] = deceased[id]["Operator"]
        heirs[heir_id]["Optional Extension"] = deceased[id]["Optional Extension"]
        heirs[heir_id]["Original $/Acre Bonus"] = deceased[id]["Original $/Acre Bonus"]
        heirs[heir_id]["Original Lessee"] = deceased[id]["Original Lessee"]
        heirs[heir_id]["PHX Operated DSU?"] = deceased[id]["PHX Operated DSU?"]
        heirs[heir_id]["PPC Exempt"] = deceased[id]["PPC Exempt"]
        heirs[heir_id]["PPC Language"] = deceased[id]["PPC Language"]
        heirs[heir_id]["Phoenix in Pay?"] = deceased[id]["Phoenix in Pay?"]
        heirs[heir_id]["Primary Term"] = deceased[id]["Primary Term"]
        heirs[heir_id]["Primary Term Expiration"] = deceased[id]["Primary Term Expiration"]
        heirs[heir_id]["Production Effective Date"] = deceased[id]["Production Effective Date"]
        heirs[heir_id]["Pugh Clause"] = deceased[id]["Pugh Clause"]
        heirs[heir_id]["Purchasing Party"] = deceased[id]["Purchasing Party"]
        heirs[heir_id]["Quarter/Quarter"] = deceased[id]["Quarter/Quarter"]
        heirs[heir_id]["Ready for Mailer?"] = deceased[id]["Ready for Mailer?"]
        heirs[heir_id]["Reporting Area"] = deceased[id]["Reporting Area"]
        heirs[heir_id]["Royalties for Flared Gas"] = deceased[id]["Royalties for Flared Gas"]
        heirs[heir_id]["Sale Effective Date"] = deceased[id]["Sale Effective Date"]
        heirs[heir_id]["Sale Executed Date"] = deceased[id]["Sale Executed Date"]
        heirs[heir_id]["Shut-In (time/$)"] = deceased[id]["Shut-In (time/$)"]
        heirs[heir_id]["Signer 2"] = user_heirs[user_heir]["Signer 2"]
        heirs[heir_id]["Signer 2 Capacity"] = user_heirs[user_heir]["Signer 2 Capacity"]
        heirs[heir_id]["Signer 2 Last Name"] = user_heirs[user_heir]["Signer 2 Last Name"]
        heirs[heir_id]["Signer 3"] = user_heirs[user_heir]["Signer 3"]
        heirs[heir_id]["Signer 3 Capacity"] = user_heirs[user_heir]["Signer 3 Capacity"]
        heirs[heir_id]["Signer 4"] = user_heirs[user_heir]["Signer 4"]
        heirs[heir_id]["Signer 5"] = user_heirs[user_heir]["Signer 5"]
        heirs[heir_id]["Signer 6"] = user_heirs[user_heir]["Signer 6"]
        heirs[heir_id]["Signer 7"] = user_heirs[user_heir]["Signer 7"]
        heirs[heir_id]["Signer 8"] = user_heirs[user_heir]["Signer 8"]
        heirs[heir_id]["Signer 9"] = user_heirs[user_heir]["Signer 9"]
        heirs[heir_id]["Sold Before?"] = deceased[id]["Sold Before?"]
        heirs[heir_id]["Spacing Unit Acreage Est."] = deceased[id]["Spacing Unit Acreage Est."]
        heirs[heir_id]["State Lease?"] = deceased[id]["State Lease?"]
        heirs[heir_id]["Survey (Full Name)"] = deceased[id]["Survey (Full Name)"]
        heirs[heir_id]["Survey"] = deceased[id]["Survey"]
        heirs[heir_id]["Suspense Requested?"] = deceased[id]["Suspense Requested?"]
        heirs[heir_id]["Title Requirement"] = deceased[id]["Title Requirement"]
        heirs[heir_id]["Total Cost to Extend"] = float(deceased[id]["Total Cost to Extend"])*float(user_heirs[user_heir]["percentage ownership"])
        heirs[heir_id]["Township Id"] = deceased[id]["Township Id"]
        heirs[heir_id]["Transaction Broker"] = deceased[id]["Transaction Broker"]
        heirs[heir_id]["Tribal Lease?"] = deceased[id]["Tribal Lease?"]
        heirs[heir_id]["Unique OGL Id"] = deceased[id]["Unique OGL Id"]
        heirs[heir_id]["Year of Acquisition"] = deceased[id]["Year of Acquisition"]

with open(output_csv_path, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(["Account Id", "Account Name", "Legal Entity", "Land Holding Type", "Total Gross Acreage", "County", "Entity Type", "Mineral Owner Royalty", "Title Source", "Title Landman", "Section Name", "Section Id", "Section", "Township", "Township Name", "Range", "State", "Tract Description", "Title Information", "Title Certification Date", "Signer 1", "Signer 1 Capacity", "Signer 1 Last Name", "Mineral Interest", "Quarter Section", "NENE NMA", "NWNE NMA", "SWNE NMA", "SENE NMA", "NENW NMA", "NWNW NMA", "SWNW NMA", "SENW NMA", "NESW NMA", "NWSW NMA", "SWSW NMA", "SESW NMA", "NESE NMA", "NWSE NMA", "SWSE NMA", "SESE NMA", "Lease Royalty", "Lease Notes & Additional Documentation", "$/Acre for Extension", "Agreement Effective Date", "Agreement Executed Date", "Area of Interest", "Abstract", "Accumulated Depletion", "Accumulated Impairment", "Accumulated Intangible Capex", "Accumulated Tangible Capex", "Additional Lands", "Additional NMA Justification", "Approximate Additional NMA", "As of Date Funds Collected", "Asset Conveyance", "Assignment Effective Date", "Assignment Executed Date", "Assignment Record ID", "Assignment Transferee", "Assignment Transferor", "Audited By", "Audited By Id", "Base OGL", "Basis Exchanged", "Basis Transferred", "Basis Written Off", "Block", "C.O.P.", "Category Factor", "Close Date", "Comments", "Consent to Assign Req?", "DSU Comments", "DSU ID #", "DSU Name", "Data Req?", "Date Election Delivered", "Date Election Sent", "Date of Election Expiration", "Deal Number", "Depths Included Leasehold", "Depths Included Mineral Estate", "Division Order Sent", "Document Effective Date", "Document Recording #", "Document Recording Date", "Elect to Participate?", "Election Certified Mail Tracking Number", "Extension Expiration", "Federal Lease?", "Finance Notes", "Force Pooled?", "Force Update?", "Funds Collected", "Funds to be Collected?", "HBP", "Holding Letter", "LH Priority", "Lease Extension Filed", "Leasehold Depth Severance?", "Legal Description [1]", "Legal Description [2]", "Legal Description [3]", "Legal Description [4]", "Marketable?", "Mineral Depth Severance?", "Mortgage Document ID", "Mortgage Effective Date", "Mortgage Executed Date", "Mortgagee", "Mortgagor", "NMA Sold", "Next Finance Follow-Up", "Non-consent Penalty", "OGL Auditor", "OGL Effective Date", "Operating Notes", "Operator", "Optional Extension", "Original $/Acre Bonus", "Original Lessee", "PHX Operated DSU?", "PPC Exempt", "PPC Language", "Phoenix in Pay?", "Primary Term", "Primary Term Expiration", "Production Effective Date", "Pugh Clause", "Purchasing Party", "Quarter/Quarter", "Ready for Mailer?", "Reporting Area", "Royalties for Flared Gas", "Sale Effective Date", "Sale Executed Date", "Shut-In (time/$)", "Signer 2", "Signer 2 Capacity", "Signer 2 Last Name", "Signer 3", "Signer 3 Capacity", "Signer 4", "Signer 5", "Signer 6", "Signer 7", "Signer 8", "Signer 9", "Sold Before?", "Spacing Unit Acreage Est.", "State Lease?", "Survey (Full Name)", "Survey", "Suspense Requested?", "Title Requirement", "Total Cost to Extend", "Township Id", "Transaction Broker", "Tribal Lease?", "Unique OGL Id", "Year of Acquisition"])
    for legal_entity in heirs:
        writer.writerow([
            heirs[legal_entity]["Account Id"],
            heirs[legal_entity]["Account Name"],
            heirs[legal_entity]["Legal Entity"],
            heirs[legal_entity]["Land Holding Type"],
            heirs[legal_entity]["Total Gross Acreage"],
            heirs[legal_entity]["County"],
            heirs[legal_entity]["Entity Type"],
            heirs[legal_entity]["Mineral Owner Royalty"],
            heirs[legal_entity]["Title Source"],
            heirs[legal_entity]["Title Landman"],
            heirs[legal_entity]["Section Name"],
            heirs[legal_entity]["Section Id"],
            heirs[legal_entity]["Section"],
            heirs[legal_entity]["Township"],
            heirs[legal_entity]["Township Name"],
            heirs[legal_entity]["Range"],
            heirs[legal_entity]["State"],
            heirs[legal_entity]["Tract Description"],
            heirs[legal_entity]["Title Information"],
            heirs[legal_entity]["Title Certification Date"],
            heirs[legal_entity]["Signer 1"],
            heirs[legal_entity]["Signer 1 Capacity"],
            heirs[legal_entity]["Signer 1 Last Name"],
            heirs[legal_entity]["Mineral Interest"],
            heirs[legal_entity]["Quarter Section"],
            heirs[legal_entity]["NENE NMA"],
            heirs[legal_entity]["NWNE NMA"],
            heirs[legal_entity]["SWNE NMA"],
            heirs[legal_entity]["SENE NMA"],
            heirs[legal_entity]["NENW NMA"],
            heirs[legal_entity]["NWNW NMA"],
            heirs[legal_entity]["SWNW NMA"],
            heirs[legal_entity]["SENW NMA"],
            heirs[legal_entity]["NESW NMA"],
            heirs[legal_entity]["NWSW NMA"],
            heirs[legal_entity]["SWSW NMA"],
            heirs[legal_entity]["SESW NMA"],
            heirs[legal_entity]["NESE NMA"],
            heirs[legal_entity]["NWSE NMA"],
            heirs[legal_entity]["SWSE NMA"],
            heirs[legal_entity]["SESE NMA"],
            heirs[legal_entity]["Lease Royalty"],
            heirs[legal_entity]["Lease Notes & Additional Documentation"],
            heirs[legal_entity]["$/Acre for Extension"],
            heirs[legal_entity]["Agreement Effective Date"],
            heirs[legal_entity]["Agreement Executed Date"],
            heirs[legal_entity]["Area of Interest"],
            heirs[legal_entity]["Abstract"],
            heirs[legal_entity]["Accumulated Depletion"],
            heirs[legal_entity]["Accumulated Impairment"],
            heirs[legal_entity]["Accumulated Intangible Capex"],
            heirs[legal_entity]["Accumulated Tangible Capex"],
            heirs[legal_entity]["Additional Lands"],
            heirs[legal_entity]["Additional NMA Justification"],
            heirs[legal_entity]["Approximate Additional NMA"],
            heirs[legal_entity]["As of Date Funds Collected"],
            heirs[legal_entity]["Asset Conveyance"],
            heirs[legal_entity]["Assignment Effective Date"],
            heirs[legal_entity]["Assignment Executed Date"],
            heirs[legal_entity]["Assignment Record ID"],
            heirs[legal_entity]["Assignment Transferee"],
            heirs[legal_entity]["Assignment Transferor"],
            heirs[legal_entity]["Audited By"],
            heirs[legal_entity]["Audited By Id"],
            heirs[legal_entity]["Base OGL"],
            heirs[legal_entity]["Basis Exchanged"],
            heirs[legal_entity]["Basis Transferred"],
            heirs[legal_entity]["Basis Written Off"],
            heirs[legal_entity]["Block"],
            heirs[legal_entity]["C.O.P."],
            heirs[legal_entity]["Category Factor"],
            heirs[legal_entity]["Close Date"],
            heirs[legal_entity]["Comments"],
            heirs[legal_entity]["Consent to Assign Req?"],
            heirs[legal_entity]["DSU Comments"],
            heirs[legal_entity]["DSU ID #"],
            heirs[legal_entity]["DSU Name"],
            heirs[legal_entity]["Data Req?"],
            heirs[legal_entity]["Date Election Delivered"],
            heirs[legal_entity]["Date Election Sent"],
            heirs[legal_entity]["Date of Election Expiration"],
            heirs[legal_entity]["Deal Number"],
            heirs[legal_entity]["Depths Included Leasehold"],
            heirs[legal_entity]["Depths Included Mineral Estate"],
            heirs[legal_entity]["Division Order Sent"],
            heirs[legal_entity]["Document Effective Date"],
            heirs[legal_entity]["Document Recording #"],
            heirs[legal_entity]["Document Recording Date"],
            heirs[legal_entity]["Elect to Participate?"],
            heirs[legal_entity]["Election Certified Mail Tracking Number"],
            heirs[legal_entity]["Extension Expiration"],
            heirs[legal_entity]["Federal Lease?"],
            heirs[legal_entity]["Finance Notes"],
            heirs[legal_entity]["Force Pooled?"],
            heirs[legal_entity]["Force Update?"],
            heirs[legal_entity]["Funds Collected"],
            heirs[legal_entity]["Funds to be Collected?"],
            heirs[legal_entity]["HBP"],
            heirs[legal_entity]["Holding Letter"],
            heirs[legal_entity]["LH Priority"],
            heirs[legal_entity]["Lease Extension Filed"],
            heirs[legal_entity]["Leasehold Depth Severance?"],
            heirs[legal_entity]["Legal Description [1]"],
            heirs[legal_entity]["Legal Description [2]"],
            heirs[legal_entity]["Legal Description [3]"],
            heirs[legal_entity]["Legal Description [4]"],
            heirs[legal_entity]["Marketable?"],
            heirs[legal_entity]["Mineral Depth Severance?"],
            heirs[legal_entity]["Mortgage Document ID"],
            heirs[legal_entity]["Mortgage Effective Date"],
            heirs[legal_entity]["Mortgage Executed Date"],
            heirs[legal_entity]["Mortgagee"],
            heirs[legal_entity]["Mortgagor"],
            heirs[legal_entity]["NMA Sold"],
            heirs[legal_entity]["Next Finance Follow-Up"],
            heirs[legal_entity]["Non-consent Penalty"],
            heirs[legal_entity]["OGL Auditor"],
            heirs[legal_entity]["OGL Effective Date"],
            heirs[legal_entity]["Operating Notes"],
            heirs[legal_entity]["Operator"],
            heirs[legal_entity]["Optional Extension"],
            heirs[legal_entity]["Original $/Acre Bonus"],
            heirs[legal_entity]["Original Lessee"],
            heirs[legal_entity]["PHX Operated DSU?"],
            heirs[legal_entity]["PPC Exempt"],
            heirs[legal_entity]["PPC Language"],
            heirs[legal_entity]["Phoenix in Pay?"],
            heirs[legal_entity]["Primary Term"],
            heirs[legal_entity]["Primary Term Expiration"],
            heirs[legal_entity]["Production Effective Date"],
            heirs[legal_entity]["Pugh Clause"],
            heirs[legal_entity]["Purchasing Party"],
            heirs[legal_entity]["Quarter/Quarter"],
            heirs[legal_entity]["Ready for Mailer?"],
            heirs[legal_entity]["Reporting Area"],
            heirs[legal_entity]["Royalties for Flared Gas"],
            heirs[legal_entity]["Sale Effective Date"],
            heirs[legal_entity]["Sale Executed Date"],
            heirs[legal_entity]["Shut-In (time/$)"],
            heirs[legal_entity]["Signer 2"],
            heirs[legal_entity]["Signer 2 Capacity"],
            heirs[legal_entity]["Signer 2 Last Name"],
            heirs[legal_entity]["Signer 3"],
            heirs[legal_entity]["Signer 3 Capacity"],
            heirs[legal_entity]["Signer 4"],
            heirs[legal_entity]["Signer 5"],
            heirs[legal_entity]["Signer 6"],
            heirs[legal_entity]["Signer 7"],
            heirs[legal_entity]["Signer 8"],
            heirs[legal_entity]["Signer 9"],
            heirs[legal_entity]["Sold Before?"],
            heirs[legal_entity]["Spacing Unit Acreage Est."],
            heirs[legal_entity]["State Lease?"],
            heirs[legal_entity]["Survey (Full Name)"],
            heirs[legal_entity]["Survey"],
            heirs[legal_entity]["Suspense Requested?"],
            heirs[legal_entity]["Title Requirement"],
            heirs[legal_entity]["Total Cost to Extend"],
            heirs[legal_entity]["Township Id"],
            heirs[legal_entity]["Transaction Broker"],
            heirs[legal_entity]["Tribal Lease?"],
            heirs[legal_entity]["Unique OGL Id"],
            heirs[legal_entity]["Year of Acquisition"]
        ])
