import json, traceback
from datetime import datetime
from typing import Optional, Final

def log(msg: str, time: Optional[datetime] = None) -> None:
    if time == None:
        time = datetime.now()
    print(f"[{time.strftime('%m/%d/%Y %H:%M')}] {msg}")

def log_exception(msg: str, err: Exception) -> None:
    time = datetime.now()
    log(msg, time)
    traceback.print_exception(err)
    log('Traceback end!', time)

class DiscordPing:
    def __init__(self, text: str):
        self._text = text

    def __str__(self) -> str:
        return self._text
    
    def __repr__(self) -> str:
        return self._text

EVERYONE_PING: Final[DiscordPing] = DiscordPing("@everyone")
HERE_PING: Final[DiscordPing] = DiscordPing("@here")

class DiscordUserPing(DiscordPing):
    def __init__(self, id: int):
        super().__init__(f"<@{id}>")
        self._id = id
    
    def __repr__(self) -> str:
        return f"user with ID {self._id}"

class DiscordRolePing(DiscordPing):
    def __init__(self, id: int):
        super().__init__(f"<@&{id}>")
        self._id = id
    
    def __repr__(self) -> str:
        return f"role with ID {self._id}"

def parse_ping(data: any) -> DiscordPing:
    if isinstance(data, str):
        pingType = str(data).lower()
        if pingType == "here":
            return HERE_PING
        elif pingType == "everyone":
            return EVERYONE_PING
        else:
            raise ValueError(f"Unknown parameterless ping type '{pingType}'")
    elif isinstance(data, dict):
        if len(data) != 1:
            raise ValueError("Ping types with more than one parameter are unsupported")
        if 'role' in data:
            return DiscordRolePing(int(data['role']))
        elif 'user' in data:
            return DiscordUserPing(int(data['user']))
        else:
            raise ValueError("Ping type was neither 'role' nor 'user'")
    else:
        raise ValueError(f"Unknown ping type '{repr(data)}' (type: {type(data)})")

class PicartoCreator:
    _creators: dict[str, 'PicartoCreator'] = {}

    @classmethod
    def get(cls, name: str) -> 'PicartoCreator':
        if name.lower() in cls._creators:
            return cls._creators[name.lower()]
        else:
            creator = cls(name)
            cls._creators[name.lower()] = creator
            return creator

    def __init__(self, name: str):
        self._id = name.lower()
        self._name = name

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    def __str__(self) -> str:
        return self._name

class DiscordServer:
    def __init__(self, name: str, webhookUrl: str, pings: list[DiscordPing]):
        self._name = name
        self._webhookUrl = webhookUrl
        
        self._pingList = pings
        self._pingStr = " ".join(map(str, pings))
        self._creators = {}
        self._creatorList = []
        self._seenCreators = []
    
    def add_creator(self, creatorName: str):
        creator = PicartoCreator.get(creatorName)
        if creator.id not in self._creators:
            self._creators[creator.id] = creator
            self._creatorList.append(creator)
    
    def update_online_creators(self, onlineCreators: list[str]):
        offlineCreators = []
        for creatorId in self._seenCreators:
            if creatorId not in onlineCreators:
                offlineCreators.append(creatorId)
                log(f"Server '{self._name}' - {str(self._creators[creatorId])} offline.")

        self._seenCreators = [creatorId for creatorId in self._seenCreators if creatorId not in offlineCreators]

        for creator in self._creators.values():
            if creator.id not in self._seenCreators and creator.id in onlineCreators:
                requests.post(self._webhookUrl, { "content": f"{self._pingStr}{str(creator)} is now online!\nhttps://picarto.tv/{str(creator)}" }, timeout = 10)
                self._seenCreators.append(creator.id)
                log(f"Server '{self._name}' - {str(creator)} online!")

    @property
    def name(self) -> str:
        return self._name

    @property
    def pings(self) -> list[DiscordPing]:
        return self._pingList
    
    @property
    def creators(self) -> list[PicartoCreator]:
        return self._creatorList

    def __str__(self) -> str:
        return self._name

if __name__ == '__main__':
    log('ADudeCalledLeo\'s Picarto Stream Notifier v1.0')
    print()

    import requests
    from time import sleep

    MOVE_TO_SECOND_DESKTOP = False

    if MOVE_TO_SECOND_DESKTOP:
        try:
            from pyvda import AppView, get_apps_by_z_order, VirtualDesktop, get_virtual_desktops

            current_window: AppView = get_apps_by_z_order()[0]

            desktops: list[VirtualDesktop] = get_virtual_desktops()
            target_desktop: VirtualDesktop = None
            if len(desktops) >= 2:
                target_desktop = desktops[1]
            else:
                target_desktop = VirtualDesktop.create()
                target_desktop.rename('Script Containment Zone')

            current_window.move(target_desktop)
        except BaseException as err:
            log_exception('Failed to move script output window to second desktop', err)

    servers: list[DiscordServer] = []

    log('Loading servers from \'servers.json\'...')
    serversJson = None
    try:
        with open('servers.json', 'rt') as f:
            serversJson = json.load(f)
    except KeyboardInterrupt:
        exit(0)
    except OSError as err:
        log("Failed to read servers.json:")
        traceback.print_exception(err)
        input("Press Enter to exit...")
        exit(1)
    
    serverIndex = 0

    for serverData in serversJson:
        serverName = ""
        try:
            serverName = str(serverData['name'])
        except KeyError:
            serverName = ""
        if len(serverName.strip()) <= 0:
            serverName = f"(unnamed server, #{serverIndex + 1})"

        serverWebhookUrl = ""
        try:
            serverWebhookUrl = str(serverData['webhook_url'])
        except KeyError:
            serverWebhookUrl = ""
        if len(serverWebhookUrl.strip()) <= 0:
            log(f"Server \"{serverName}\" - missing webhook URL, skipping")
            continue
        
        serverCreators: list[str] = []
        
        serverCreatorData = None
        try:
            serverCreatorData = serverData['creators']
        except KeyError:
            log(f"Server \"{serverName}\" - missing creator list, skipping")
            continue
         
        if isinstance(serverCreatorData, list):
           for i, data in enumerate(serverCreatorData):
                if isinstance(data, str):
                    serverCreators.append(data)
                else:
                    log(f"Server \"{serverName}\" - invalid creator name {data}")
        elif isinstance(serverCreatorData, str):
            serverCreators.append(serverCreatorData)
        else:
            log(f"Server \"{serverName}\" - invalid creator list {serverCreatorData}, skipping")
            continue

        serverPings: list[DiscordPing] = []
        
        serverPingData = None
        try:
            serverPingData = serverData['pings']
        except KeyError:
            log(f"Server \"{serverName}\" - missing ping configuration, defaulting to @everyone'")
            serverPings.append(EVERYONE_PING)

        if isinstance(serverPingData, list):
            for i, data in enumerate(serverPingData):
                try:
                    serverPings.append(parse_ping(data))
                except ValueError as err:
                    log_exception(f"Server \"{serverName}\" - failed to parse ping configuration at index {i}", err)
        elif serverPingData:
            try:
                serverPings.append(parse_ping(serverPingData))
            except ValueError as err:
                log_exception(f"Server \"{serverName}\" - failed to parse ping configuration", err)
        
        server = DiscordServer(serverName, serverWebhookUrl, serverPings)

        for creatorName in serverCreators:
            server.add_creator(creatorName)
        
        servers.append(server)
        serverIndex += 1
    
    print()
    
    if serverIndex == 0:
        log('No configured servers. Exiting...')
        exit(0)
    
    serverList = f"{serverIndex} configured server(s):"
    serverIdxLen = len(str(serverIndex))
    for i, server in enumerate(servers):
        serverList += f"\n{str(i + 1).rjust(serverIdxLen, ' ')}) {server.name}:"
        serverList += f"\n    {len(server.creators)} creator(s): {', '.join(map(str, server.creators))}"
        serverList += f"\n    {len(server.pings)} ping(s): {', '.join(map(repr, server.pings))}"
    log(serverList)
    print()

    while True:
        success: bool = True
        onlineCreators: list[str] = []

        try:
            #log('Checking for online creators...')
            onlineJson = json.loads(requests.get('https://api.picarto.tv/api/v1/online?adult=true&gaming=true',
                headers = {
                    "User-Agent": "ADudeCalledLeo's Picarto Stream Notifier/1.0",
                    "From": "kfir40mailminer@gmail.com"
                }, timeout = 10).text)
            for creatorData in onlineJson:
                onlineCreators.append(str(creatorData['name']).lower())
        except KeyboardInterrupt:
            exit(0)
        except BaseException as err:
            success = False
            log_exception('Failed to fetch online creators!', err)
        
        if success:
            for server in servers:
                try:
                    server.update_online_creators(onlineCreators)
                except KeyboardInterrupt:
                    exit(0)
                except BaseException as err:
                    log_exception(f"Server \"{str(server)}\" - failed to update online creators", err)

        try:
            sleep(60)
        except KeyboardInterrupt:
            break
