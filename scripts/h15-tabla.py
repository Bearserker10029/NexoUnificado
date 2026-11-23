import json,csv
MAP={"alpine:3.20":"alpine:3.22","docker:27-cli":"docker:28-cli","nginx:1.27-alpine":"nginx:1.29-alpine","prom/prometheus:v2.55.1":"prom/prometheus:v3.5.0","prom/node-exporter:v1.8.2":"prom/node-exporter:v1.9.1","prom/blackbox-exporter:v0.25.0":"prom/blackbox-exporter:v0.27.0","grafana/grafana:11.3.0":"grafana/grafana:11.6.0"}
fn=lambda i:i.replace('/','_').replace(':','_')
def load(fase,img):
    d=json.load(open(f"evidencias/h15/{fase}/{fn(img)}.json",encoding='utf-8'));s={}
    for r in d.get("Results") or []:
        for v in r.get("Vulnerabilities") or []:
            s[(v["VulnerabilityID"],v["PkgName"])]=v
    return s
rows=[];res=[]
for a,b in MAP.items():
    A=load("antes",a);B=load("despues",b)
    res.append((a,b,len(A),sum(1 for v in A.values() if v["Severity"]=="CRITICAL"),len(B),sum(1 for v in B.values() if v["Severity"]=="CRITICAL"),len(set(A)-set(B)),len(set(B)-set(A))))
    for k,v in sorted(A.items(),key=lambda x:(x[1]["Severity"]!="CRITICAL",x[0])):
        post="Corregida" if k not in B else "Persiste ("+("sin parche" if not B[k].get("FixedVersion") else "parche: "+B[k]["FixedVersion"])+")"
        rows.append([a,k[0],k[1],v["Severity"],v["InstalledVersion"],v.get("FixedVersion","sin parche"),f"{a} -> {b}",post])
with open("evidencias/h15/tabla-vulnerabilidades.csv","w",newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(["imagen","CVE","paquete","severidad","version_inicial","version_con_parche","correccion_aplicada","resultado_posterior"]);w.writerows(rows)
with open("evidencias/h15/tabla-resumen.md","w",encoding="utf-8") as f:
    f.write("| Imagen inicial | Imagen corregida | HIGH+CRIT antes (CRIT) | HIGH+CRIT despues (CRIT) | CVE corregidos | CVE nuevos |\n|---|---|---|---|---|---|\n")
    for r in res: f.write(f"| {r[0]} | {r[1]} | {r[2]} ({r[3]}) | {r[4]} ({r[5]}) | {r[6]} | {r[7]} |\n")
    f.write("\n## CVE CRITICAL (imagen, CVE, paquete, version inicial, correccion, resultado)\n\n| Imagen | CVE | Paquete | Version inicial | Correccion aplicada | Resultado posterior |\n|---|---|---|---|---|---|\n")
    for r in rows:
        if r[3]=="CRITICAL": f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[4]} | {r[6]} (parche: {r[5]}) | {r[7]} |\n")
