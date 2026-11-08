import httpx
import time

headers = {'X-API-Key': 'change-me'}
res = httpx.post(
    'http://127.0.0.1:8031/admin/register/outlook/batch',
    json={'count': 1, 'rate_per_minute': 10, 'mode': 'outlook'},
    headers=headers,
    timeout=10.0,
)
print('Start job response:', res.status_code, res.json())

seen = set()
for i in range(50):
    time.sleep(3)
    try:
        st = httpx.get('http://127.0.0.1:8031/admin/register/outlook/status', headers=headers, timeout=5.0).json()
    except Exception as exc:
        print('Poll error:', exc)
        continue
    status = st.get('status')
    logs = st.get('recent_logs', [])
    for l in logs:
        if l not in seen:
            seen.add(l)
            prog = st.get('progress')
            tot = st.get('total')
            print(f'[{prog}/{tot}] {l}')
    if status in ('FINISHED', 'FAILED', 'CANCELLED'):
        print('Final Status reached:', status, 'Succeeded:', st.get('success_count'), 'Failed:', st.get('failed_count'))
        break
