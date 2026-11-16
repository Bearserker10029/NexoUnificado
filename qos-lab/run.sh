#!/bin/bash
# H8 - Laboratorio de QoS: mide la voz con y sin QoS bajo congestión.
# Dos espacios de red (cli y srv) unidos por un enlace con cuello de botella.
# Voz = UDP marcado EF (DSCP 46), 64 kbps como G.711. Congestión = TCP masivo.
set -u
OUT=${OUT:-/out}
DUR=${DUR:-30}          # segundos por prueba
RATE=${RATE:-10mbit}    # cuello de botella (simula el enlace a Internet)
mkdir -p "$OUT"

cleanup() { pkill iperf3 2>/dev/null; ip netns del cli 2>/dev/null; ip netns del srv 2>/dev/null; }
trap cleanup EXIT
cleanup; sleep 1

setup_red() {
  ip netns add cli; ip netns add srv
  ip link add veth-cli type veth peer name veth-srv
  ip link set veth-cli netns cli; ip link set veth-srv netns srv
  ip -n cli addr add 10.9.0.1/24 dev veth-cli; ip -n srv addr add 10.9.0.2/24 dev veth-srv
  ip -n cli link set veth-cli up; ip -n srv link set veth-srv up
  ip -n cli link set lo up;       ip -n srv link set lo up
  # Evita que el desplazamiento de segmentación oculte el cuello de botella.
  ip netns exec cli ethtool -K veth-cli tso off gso off gro off >/dev/null 2>&1
}

qdisc_sin_qos() {
  # Una sola cola FIFO tras el cuello de botella: todo el tráfico compite igual.
  ip netns exec cli tc qdisc replace dev veth-cli root tbf rate $RATE burst 15k limit 200k
}

qdisc_con_qos() {
  # HTB por clases + fq_codel, clasificando por DSCP (diseño de la sección 4.4 del informe TA1).
  local d=veth-cli
  ip netns exec cli tc qdisc replace dev $d root handle 1: htb default 60
  ip netns exec cli tc class add dev $d parent 1:  classid 1:1  htb rate $RATE ceil $RATE
  ip netns exec cli tc class add dev $d parent 1:1 classid 1:10 htb rate 2mbit ceil $RATE prio 0   # EF voz
  ip netns exec cli tc class add dev $d parent 1:1 classid 1:20 htb rate 4mbit ceil $RATE prio 1   # AF41 video
  ip netns exec cli tc class add dev $d parent 1:1 classid 1:30 htb rate 1mbit ceil $RATE prio 2   # CS3 señalización
  ip netns exec cli tc class add dev $d parent 1:1 classid 1:60 htb rate 3mbit ceil $RATE prio 3   # resto
  for c in 10 20 30 60; do ip netns exec cli tc qdisc add dev $d parent 1:$c fq_codel 2>/dev/null || ip netns exec cli tc qdisc add dev $d parent 1:$c pfifo limit 100; done
  ip netns exec cli tc filter add dev $d parent 1: protocol ip prio 1 u32 match ip dsfield 0xb8 0xfc flowid 1:10
  ip netns exec cli tc filter add dev $d parent 1: protocol ip prio 2 u32 match ip dsfield 0x88 0xfc flowid 1:20
  ip netns exec cli tc filter add dev $d parent 1: protocol ip prio 3 u32 match ip dsfield 0x60 0xfc flowid 1:30
}

prueba() {   # $1 = nombre de la fase
  local f=$1
  echo "=== Fase: $f ==="
  ip netns exec srv iperf3 -s -p 5201 -D --logfile /dev/null
  ip netns exec srv iperf3 -s -p 5202 -D --logfile /dev/null
  sleep 1
  ip netns exec srv tcpdump -i veth-srv -c 60 -w "$OUT/${f}_voz.pcap" udp port 5201 >/dev/null 2>&1 &
  local tp=$!
  # Congestión: 4 flujos TCP masivos (video/archivos) saturando el enlace.
  ip netns exec cli iperf3 -c 10.9.0.2 -p 5202 -P 4 -t $((DUR+4)) --dscp 0 -J > "$OUT/${f}_bulk.json" 2>/dev/null &
  local bp=$!
  sleep 3
  # Latencia de un paquete marcado EF durante la congestión.
  ip netns exec cli ping -Q 0xb8 -i 0.2 -c $((DUR*5)) 10.9.0.2 > "$OUT/${f}_ping.txt" 2>&1 &
  local pp=$!
  # Voz: UDP 64 kbps, paquetes de 160 B, DSCP EF (46).
  ip netns exec cli iperf3 -c 10.9.0.2 -p 5201 -u -b 64k -l 160 -t $DUR --dscp 46 -J > "$OUT/${f}_voz.json" 2>/dev/null
  wait $pp; wait $bp 2>/dev/null; kill $tp 2>/dev/null; pkill iperf3; sleep 1
  ip netns exec cli tc -s qdisc show dev veth-cli > "$OUT/${f}_tc.txt"
  ip netns exec cli tc -s class show dev veth-cli >> "$OUT/${f}_tc.txt" 2>/dev/null
}

resumen() {
python3 - "$OUT" <<'PY'
import json,re,sys,math
out=sys.argv[1]
def mos(owd,loss):
    # Modelo E simplificado (G.711 con ocultación de pérdidas, Bpl=4.3)
    d=owd; Id=0.024*d+(0.11*(d-177.3) if d>177.3 else 0)
    Ie=95*loss/(loss+4.3); R=93.2-Id-Ie
    return R,(1+0.035*R+7e-6*R*(R-60)*(100-R)) if 0<R<100 else (1 if R<=0 else 4.5)
lines=["H8 - Voz bajo congestión (cuello de botella, por fase)",""]
rows={}
for f,name in (("sin_qos","SIN QoS"),("con_qos","CON QoS")):
    try:
        v=json.load(open(f"{out}/{f}_voz.json"))["end"]["sum"]
        jit,loss=v["jitter_ms"],v["lost_percent"]
        p=open(f"{out}/{f}_ping.txt").read()
        m=re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",p)
        rmin,ravg,rmax,rdev=map(float,m.groups()); owd=ravg/2
        pl=re.search(r"([\d.]+)% packet loss",p)
        R,M=mos(owd,loss)
        rows[f]=(jit,loss,owd,rmax/2,M)
        lines+= [f"{name}:",
          f"  Jitter de la voz ........ {jit:.2f} ms   (objetivo <= 30 ms)",
          f"  Pérdida de la voz ....... {loss:.2f} %    (objetivo <= 1 %)",
          f"  Latencia un sentido ..... {owd:.1f} ms promedio, {rmax/2:.1f} ms máximo (RTT/2 de un ping EF; objetivo <= 150 ms)",
          f"  Factor R / MOS estimado . {R:.1f} / {M:.2f}   (objetivo MOS >= 3,8)",""]
    except Exception as e:
        lines.append(f"{name}: sin datos ({e})")
open(f"{out}/resumen_h8.txt","w").write("\n".join(lines)+"\n")
print("\n".join(lines))
PY
}

echo "Cuello de botella: $RATE   Duración por fase: ${DUR}s"
setup_red
qdisc_sin_qos; prueba sin_qos
qdisc_con_qos; prueba con_qos
resumen
echo "Resultados en $OUT"
