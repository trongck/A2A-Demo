import urllib.request
import json

base_url = 'http://127.0.0.1:8000'

# 1. Login
login_data = json.dumps({'username': 'ai20k', 'password': '123456'}).encode()
req = urllib.request.Request(f'{base_url}/admin/auth/login', data=login_data, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    res = json.loads(resp.read().decode())
    token = res['access_token']
    user = res['user']
    print('[PASS] Login successful:', user['username'], '| role:', user['role'])

auth_headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# 2. Get /admin/auth/me
req = urllib.request.Request(f'{base_url}/admin/auth/me', headers=auth_headers)
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    me = json.loads(resp.read().decode())
    print('[PASS] /admin/auth/me:', me['display_name'])

# 3. Get /admin/crowd/overview
req = urllib.request.Request(f'{base_url}/admin/crowd/overview', headers=auth_headers)
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    crowd = json.loads(resp.read().decode())
    print(f'[PASS] /admin/crowd/overview: {len(crowd["zones"])} zones, {crowd["total_attractions"]} attractions')

# 4. Get /admin/bookings/stats
req = urllib.request.Request(f'{base_url}/admin/bookings/stats', headers=auth_headers)
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    stats = json.loads(resp.read().decode())
    print('[PASS] /admin/bookings/stats:', stats)

# 5. Get /admin/bookings list
req = urllib.request.Request(f'{base_url}/admin/bookings?page=1&page_size=5', headers=auth_headers)
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    bookings = json.loads(resp.read().decode())
    print(f'[PASS] /admin/bookings: {bookings["total"]} total bookings found')

# 6. Get /admin/map/graph
req = urllib.request.Request(f'{base_url}/admin/map/graph', headers=auth_headers)
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    graph = json.loads(resp.read().decode())
    print(f'[PASS] /admin/map/graph: {len(graph["nodes"])} nodes, {len(graph["edges"])} edges')

hub_id = next(node['node_id'] for node in graph['nodes'] if node['type'] == 'hub')
poi_id = next(node['node_id'] for node in graph['nodes'] if node['type'] == 'poi')

# 7. Get /admin/map/path (Dijkstra)
req = urllib.request.Request(f'{base_url}/admin/map/path?from_node={hub_id}&to_node={poi_id}', headers=auth_headers)
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    path = json.loads(resp.read().decode())
    print(f'[PASS] /admin/map/path: path={path["path_nodes"]}, walking_minutes={path["total_walking_minutes"]}')

# 8. PATCH /admin/crowd/{placeId}
patch_data = json.dumps({'current_people': 75, 'wait_minutes': 10}).encode()
req = urllib.request.Request(f'{base_url}/admin/crowd/{poi_id}', data=patch_data, headers=auth_headers, method='PATCH')
with urllib.request.urlopen(req) as resp:
    assert resp.status == 200
    patched = json.loads(resp.read().decode())
    print('[PASS] PATCH /admin/crowd/{placeId} successful')

# 9. GET /admin/bookings/{session_id} and confirm
if bookings['items']:
    sid = bookings['items'][0]['session_id']
    detail_req = urllib.request.Request(f'{base_url}/admin/bookings/{sid}', headers=auth_headers)
    with urllib.request.urlopen(detail_req) as detail_resp:
        assert detail_resp.status == 200
        detail = json.loads(detail_resp.read().decode())
        print(f'[PASS] /admin/bookings/{sid}: {len(detail["plans"])} plans found')
        
    if detail['plans']:
        confirm_data = json.dumps({'plan_id': detail['plans'][0]['plan_id'], 'note': 'Automated test note'}).encode()
        confirm_req = urllib.request.Request(f'{base_url}/admin/bookings/{sid}/confirm', data=confirm_data, headers=auth_headers)
        with urllib.request.urlopen(confirm_req) as cr:
            assert cr.status == 200
            print(f'[PASS] POST /admin/bookings/{sid}/confirm successful')

print('\n>>> ALL 9 ADMIN TESTS PASSED! <<<')
