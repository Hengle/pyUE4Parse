from UE4Parse.Provider.Vfs.DirectoryStorageProvider import DirectoryStorageProvider
from UE4Parse.Provider.Vfs.DirectoryStorage import DirectoryStorage
from UE4Parse import BinaryReader
from UE4Parse.Versions.Versions import VersionContainer
from UE4Parse.Exceptions.Exceptions import InvalidEncryptionKey
from abc import ABC
from typing import Any, BinaryIO, IO, Optional, Tuple, Union, Dict, List
from io import BytesIO
from UE4Parse.IO import FFileIoStoreReader

from UE4Parse.Assets.Objects.FGuid import FGuid
from UE4Parse.Encryption import FAESKey
from UE4Parse.IoObjects.FIoGlobalData import FIoGlobalData
from UE4Parse.Logger import logger
from UE4Parse.PakFile.PakReader import PakReader


class AbstractVfsFileProvider(ABC):
    IsCaseInsensitive: bool
    GlobalData: Optional[FIoGlobalData]
    UnloadedContainers: List[Union[FFileIoStoreReader, PakReader]]
    LoadedContainers: List[Union[FFileIoStoreReader, PakReader]]
    _files: DirectoryStorageProvider

    def __init__(self, versions: VersionContainer, isCaseInsensitive: bool = False) -> None:
        self.GlobalData = None
        self.Versions = versions
        self.IsCaseInsensitive = isCaseInsensitive
        self.UnloadedContainers = []
        self.LoadedContainers = []
        self._files = DirectoryStorageProvider(self.IsCaseInsensitive)

    def register_container(self, name, streams: Tuple[BinaryIO]):
        """
        Initializes container reader and adds it to `UnloadedContainers`
        """
        if name.endswith(".pak"):
            try:
                logger.debug(f"Registering PakFile: {name}")
                reader = PakReader(name, self.IsCaseInsensitive, streams[0])
                self.UnloadedContainers.append(reader)
            except Exception as e:
                logger.error(f"Error reading {name}: {e}")
        elif name.endswith(".utoc"):
            logger.debug(f"Registering IoStore: {name[:-5]}")
            try:
                reader = FFileIoStoreReader(name, streams[0],
                                            streams[1], self.IsCaseInsensitive)
                self.UnloadedContainers.append(reader)
            except Exception as e:
                logger.error(f"Error reading {name}: {e}")
        else:
            pass

    def unloaded_files_by_guid(self, guid: Union[str, FGuid]) -> List[Union[FFileIoStoreReader, PakReader]]:
        files = []
        for x in self.UnloadedContainers:
            enc_guid = x.get_encryption_key_guid()
            if enc_guid == guid:
                files.append(x)
        return files

    def submit_key(self, guid: Union[str, FGuid], key: Optional[FAESKey]) -> int:
        """
        Tries to mount a file with the given guid
        returns: `int` the number of files successfully mounted

        Arguments: \n
        guid -- the guid of the file to mount \n
        key -- the key to use for the encryption
        """
        return self.submit_keys({guid: key})

    def submit_keys(self, keys: Dict[Union[str, FGuid], Optional[FAESKey]]) -> int:
        """
        Tries to mount a file with the given guid
        returns: `int` the number of files successfully mounted

        Arguments: \n
        `dict` of guid and key \n
        guid -- the guid of the file to mount \n
        key -- the key to use for the encryption
        """
        return self._mount(keys)

    def _mount(self, keys: Dict[Union[str, FGuid], Optional[FAESKey]]):
        mount_count = 0
        for guid, key in keys.items():
            for x in self.unloaded_files_by_guid(guid):
                if isinstance(x, FFileIoStoreReader):
                    if x.IsEncrypted and x.get_encryption_key_guid() not in keys:
                        continue
                    if not x.HasDirectoryIndex:
                        continue
                    try:
                        index, chunks = x.ReadDirectoryIndex(keys[x.get_encryption_key_guid()])
                        del chunks
                        self._files.add_index(index, x)
                        self.LoadedContainers.append(x)
                        self.UnloadedContainers.remove(x)
                        mount_count += 1
                    except Exception as e:
                        if isinstance(e, InvalidEncryptionKey):
                            continue
                        logger.error(f"Error reading index for {x.FileName}, {e}")
                elif isinstance(x, PakReader):
                    if x.Info.bEncryptedIndex and x.get_encryption_key_guid() not in keys:
                        continue
                    try:
                        index = x.ReadIndex(keys[x.get_encryption_key_guid()])
                        self._files.add_index(index, x)

                        self.LoadedContainers.append(x)
                        self.UnloadedContainers.remove(x)
                        mount_count += 1
                    except Exception as e:
                        if isinstance(e, InvalidEncryptionKey):
                            continue
                        logger.error(f"Error reading index for {x.FileName}, {e}")
                else:
                    continue
        return mount_count