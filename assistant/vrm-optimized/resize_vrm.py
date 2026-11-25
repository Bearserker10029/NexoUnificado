import json, struct, sys, io
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
max_size = int(sys.argv[3]) if len(sys.argv) > 3 else 2048

data = open(src, 'rb').read()
magic, version, length = struct.unpack_from('<III', data, 0)
assert magic == 0x46546C67, 'no es un GLB'

offset, json_chunk, bin_chunk, other_chunks = 12, None, None, []
while offset < length:
    clen, ctype = struct.unpack_from('<II', data, offset)
    cdata = data[offset + 8: offset + 8 + clen]
    if ctype == 0x4E4F534A:
        json_chunk = cdata
    elif ctype == 0x004E4942:
        bin_chunk = cdata
    else:
        other_chunks.append((ctype, cdata))
    offset += 8 + clen

gltf = json.loads(json_chunk)
bin_data = bin_chunk

def resized(payload, tag):
    try:
        img = Image.open(io.BytesIO(bytes(payload)))
        img.load()
    except Exception:
        print('  no decodifica, se deja igual:', tag, len(payload), 'bytes, magic', payload[:8].hex())
        return None
    if max(img.size) <= max_size:
        return None
    print('  reducida:', tag, img.size, '->', (min(img.width, max_size), min(img.height, max_size)))
    img = img.resize((min(img.width, max_size), min(img.height, max_size)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()

image_bvs = {}
for img in gltf.get('images', []):
    if 'bufferView' in img:
        image_bvs[img['bufferView']] = img.get('name', '') or img.get('mimeType', 'imagen')

new_bin, new_views, cursor = bytearray(), [], 0
for i, bv in enumerate(gltf.get('bufferViews', [])):
    start = bv.get('byteOffset', 0)
    payload = bin_data[start:start + bv['byteLength']]
    if i in image_bvs:
        r = resized(payload, 'bufferView %d (%s)' % (i, image_bvs[i]))
        if r:
            payload = r
    pad = (4 - len(payload) % 4) % 4
    payload = payload + b'\x00' * pad
    nbv = dict(bv)
    nbv['byteOffset'] = cursor
    nbv['byteLength'] = len(payload) - pad
    new_views.append(nbv)
    new_bin += payload
    cursor += len(payload)

gltf['bufferViews'] = new_views
gltf['buffers'][0]['byteLength'] = len(new_bin)

new_json = json.dumps(gltf, separators=(',', ':')).encode()
new_json += b' ' * ((4 - len(new_json) % 4) % 4)

chunks = [(0x4E4F534A, new_json), (0x004E4942, bytes(new_bin))] + other_chunks
total = 12 + sum(8 + len(c) for _, c in chunks)
with open(dst, 'wb') as f:
    f.write(struct.pack('<III', 0x46546C67, version, total))
    for ctype, cdata in chunks:
        f.write(struct.pack('<II', len(cdata), ctype))
        f.write(cdata)
print('OK:', src, '->', dst)