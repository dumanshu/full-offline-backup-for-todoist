#!/usr/bin/python3
""" Utility to download the attachments associated with a Todoist backup VFS
    The downloaded attachments are packed to the same VFS """

import re
import json
import itertools
import os
from typing import Set, List, Optional
from .utils import sanitize_file_name
from .backup_downloader import SYNC_DATA_FILENAME
from .virtual_fs import VirtualFs
from .tracer import Tracer
from .url_downloader import URLDownloader

class TodoistAttachmentInfo:
    """ Represents the properties of a Todoist attachment """
    file_name: str
    file_url: str

    def __init__(self, file_name: str, file_url: str):
        self.file_name = file_name
        self.file_url = file_url

class TodoistBackupAttachmentsDownloader:
    """ Provides utilities for downloading the attachments of a Todoist backup """

    __TODOIST_ATTACHMENT_REGEXP = re.compile(r"\[\[\s*file\s*(.+)\s*\]\]")
    __ATTACHMENT_FOLDER = "attachments/"

    __tracer: Tracer
    __urldownloader: URLDownloader

    def __init__(self, tracer: Tracer, urldownloader: URLDownloader):
        self.__tracer = tracer
        self.__urldownloader = urldownloader

    @staticmethod
    def __attachment_from_dict(data: dict) -> Optional[TodoistAttachmentInfo]:
        if "file_name" not in data or "file_url" not in data:
            return None
        return TodoistAttachmentInfo(sanitize_file_name(data["file_name"]), data["file_url"])

    def __fetch_attachment_infos(self, vfs: VirtualFs) -> List[TodoistAttachmentInfo]:
        self.__tracer.trace("Reading sync data from VFS...")

        sync_raw = vfs.read_file(SYNC_DATA_FILENAME).decode("utf-8")
        sync_data = json.loads(sync_raw)

        attachment_infos: List[TodoistAttachmentInfo] = []

        # Attachments embedded in task content via [[ file {...} ]] syntax
        for item in sync_data.get("items", []):
            content = item.get("content", "")
            for match_str in self.__TODOIST_ATTACHMENT_REGEXP.findall(content):
                try:
                    info = self.__attachment_from_dict(json.loads(match_str))
                    if info:
                        attachment_infos.append(info)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Attachments on comments/notes via file_attachment field
        for note in sync_data.get("notes", []):
            fa = note.get("file_attachment")
            if fa and isinstance(fa, dict):
                info = self.__attachment_from_dict(fa)
                if info:
                    attachment_infos.append(info)

        # Project-level comments also have file_attachment
        for pnote in sync_data.get("project_notes", []):
            fa = pnote.get("file_attachment")
            if fa and isinstance(fa, dict):
                info = self.__attachment_from_dict(fa)
                if info:
                    attachment_infos.append(info)

        self.__tracer.trace(f"Found {len(attachment_infos)} attachments in sync data")
        return attachment_infos

    @staticmethod
    def __deduplicate_file_name(original_file_name: str, file_names_to_avoid: Set[str]) -> str:
        """ Modifies the given file name in order to avoid all of the file names
           in the given list of file names to avoid """
        name_without_ext, ext = os.path.splitext(original_file_name)
        for i in itertools.count(2):
            new_file_name = name_without_ext + "_" + str(i) + ext
            if new_file_name not in file_names_to_avoid:
                return new_file_name

        assert False, "Unreachable code" # pragma: no cover

    def __deduplicate_attachments_names(self,
                                        attachment_infos: List[TodoistAttachmentInfo]) -> None:
        """ Modifies the attachment names, if necessary, in order to
            avoid duplicate file names """
        included_attachment_names: Set[str] = set()

        for attachment_info in attachment_infos:
            if attachment_info.file_name in included_attachment_names:
                new_file_name = self.__deduplicate_file_name(
                    attachment_info.file_name, included_attachment_names)
                self.__tracer.trace("Duplicate attachment name found - "
                    f"Renaming {attachment_info.file_name} to {new_file_name}...")
                attachment_info.file_name = new_file_name

            included_attachment_names.add(attachment_info.file_name)

    def __download_and_pack_attachments(self, attachment_infos: List[TodoistAttachmentInfo],
                                              vfs: VirtualFs) -> None:
        """ Downloads and packs the given attachments in a folder 'attachments'
            of the current Todoist backup VFS """
        for idx, attachment_info in enumerate(attachment_infos):
            self.__tracer.trace(f"[{idx+1}/{len(attachment_infos)}] "
                f"Downloading attachment '{attachment_info.file_name}'...")

            data = self.__urldownloader.get(attachment_info.file_url)

            vfs.write_file(self.__ATTACHMENT_FOLDER + attachment_info.file_name, data)

            self.__tracer.trace(f"[{idx+1}/{len(attachment_infos)}] "
                f"Downloaded attachment '{attachment_info.file_name}'...")

    def download_attachments(self, vfs: VirtualFs) -> None:
        """ Downloads all the attachments of the current Todoist backup VFS
            and packs them in a folder 'attachments' to the same VFS """

        # Ensure that we haven't already processed this file...
        if any(name.startswith(self.__ATTACHMENT_FOLDER) for name in vfs.file_list()):
            self.__tracer.trace("File already has attachments folder, skipping.")
            return

        # Fetch the information of all the attachments
        attachment_infos = self.__fetch_attachment_infos(vfs)
        self.__tracer.trace(f"Found {len(attachment_infos)} attachments.")
        self.__deduplicate_attachments_names(attachment_infos)
        self.__download_and_pack_attachments(attachment_infos, vfs)
