import urllib.request
import os
import json

os.makedirs("static", exist_ok=True)

screens = [
    {"name": "ai_command_center.html", "url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzAwMDY1NDBjNGRkNWQ2MWMwOTM0ZjU0YjViMzE5NzUwEgsSBxCqu5ac8h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxMTg4OTYyNjI3Nzg3NzgzNTg1OQ&filename=&opi=89354086"},
    {"name": "clinical_dossier.html", "url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzAwMDY1NDBjNGRkNWQ2MjMwOTM0ZjU0YjViMzE5NzUwEgsSBxCqu5ac8h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxMTg4OTYyNjI3Nzg3NzgzNTg1OQ&filename=&opi=89354086"},
    {"name": "landing_experience.html", "url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzAwMDY1NDBjNGRkNWQ2MWUwOTM0ZjU0YjViMzE5NzUwEgsSBxCqu5ac8h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxMTg4OTYyNjI3Nzg3NzgzNTg1OQ&filename=&opi=89354086"},
    {"name": "mission_control_queue.html", "url": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ8Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpbCiVodG1sXzAwMDY1NDBjNGRkNWQ2MjAwOTM0ZjU0YjViMzE5NzUwEgsSBxCqu5ac8h4YAZIBJAoKcHJvamVjdF9pZBIWQhQxMTg4OTYyNjI3Nzg3NzgzNTg1OQ&filename=&opi=89354086"},
]

for screen in screens:
    print(f"Downloading {screen['name']}...")
    try:
        urllib.request.urlretrieve(screen['url'], os.path.join("static", screen['name']))
        print(f"Saved {screen['name']}")
    except Exception as e:
        print(f"Error downloading {screen['name']}: {e}")
