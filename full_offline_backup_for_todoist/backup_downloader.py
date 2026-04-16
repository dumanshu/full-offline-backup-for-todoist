#!/usr/bin/python3
""" Class to download Todoist backup ZIPs using the Todoist API """
import datetime
import json
from .utils import sanitize_file_name
from .tracer import Tracer
from .todoist_api import TodoistApi
from .virtual_fs import VirtualFs

SYNC_DATA_FILENAME = "sync_data.json"

class TodoistBackupDownloader:
    """ Class to download Todoist backup ZIPs using the Todoist API """
    __tracer: Tracer
    __todoist_api: TodoistApi

    def __init__(self, tracer: Tracer, todoist_api: TodoistApi):
        self.__tracer = tracer
        self.__todoist_api = todoist_api

    def download(self, vfs: VirtualFs) -> None:
        """ Generates a Todoist backup and saves it to the given VFS """
        self.__tracer.trace("Generating backup from current Todoist status")

        backup_version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        vfs.set_path_hint(sanitize_file_name("TodoistBackup_" + backup_version))

        if vfs.existed():
            self.__tracer.trace("File already downloaded... skipping")
            return

        self.__tracer.trace("Fetching full sync data from Todoist API...")
        sync_data = self.__todoist_api.get_full_sync()

        self.__tracer.trace("Saving full sync data as JSON...")
        vfs.write_file(SYNC_DATA_FILENAME,
                        json.dumps(sync_data, indent=2, ensure_ascii=False).encode("utf-8"))

        projects = sync_data.get("projects", [])
        items = sync_data.get("items", [])
        sections = sync_data.get("sections", [])
        notes = sync_data.get("notes", [])

        items_by_project: dict = {}
        for item in items:
            pid = item.get("project_id", "unknown")
            items_by_project.setdefault(pid, []).append(item)

        sections_by_project: dict = {}
        for section in sections:
            pid = section.get("project_id", "unknown")
            sections_by_project.setdefault(pid, []).append(section)

        notes_by_item: dict = {}
        for note in notes:
            iid = note.get("item_id", "unknown")
            notes_by_item.setdefault(iid, []).append(note)

        for project in projects:
            pid = project.get("id", "unknown")
            pname = project.get("name", "Unknown")
            project_data = {
                "project": project,
                "sections": sections_by_project.get(pid, []),
                "items": items_by_project.get(pid, []),
                "notes": {
                    item_id: notes_by_item[item_id]
                    for item_id in [i.get("id") for i in items_by_project.get(pid, [])]
                    if item_id in notes_by_item
                },
            }
            fname = f"{sanitize_file_name(pname)} [{pid}].json"
            vfs.write_file(fname,
                            json.dumps(project_data, indent=2, ensure_ascii=False).encode("utf-8"))
            self.__tracer.trace(f"Saved project '{pname}' ({len(items_by_project.get(pid, []))} items)")
