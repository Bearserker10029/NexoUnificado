import json,glob,sys,os
fase=sys.argv[1]
for f in sorted(glob.glob(f"evidencias/h15/{fase}/*.json")):
    d=json.load(open(f,encoding='utf-8'))
    tot=fix=0; crit=0
    for r in d.get("Results",[]) or []:
        for v in r.get("Vulnerabilities",[]) or []:
            tot+=1; fix+=bool(v.get("FixedVersion")); crit+=v["Severity"]=="CRITICAL"
    print(f"{d.get('ArtifactName'):50} total={tot:4} crit={crit:3} conparche={fix:4}")
