from struct import Struct
import time

from durator.db.database import db_connection
from durator.world.game.account_data import AccountData, AccountDataTypeMask
from durator.world.game.char.character_data import CharacterData
from durator.world.game.object_manager import OBJECT_MANAGER
from durator.world.game.update_object_packet import PlayerSpawnPacket
from durator.world.opcodes import OpCode
from durator.world.world_connection_state import WorldConnectionState
from durator.world.world_packet import WorldPacket
from pyshgck.logger import LOG


class PlayerLoginHandler(object):
    """ Handle the player entering in world. """

    # We should answer with a validation and a few more informations. Some
    # things that are sent to the client right after on Mangos Classic are:
    # - send server message of the day
    # - send guild message of the day
    # - check if character is dead, then send corpse reclaim timer
    # - set the rest value
    # - set the homebind
    # - possibly send cinematic if it's a first login
    # - set time speed
    # - maybe teleport player back to his homebind
    # - send friend and ignore list
    # - send stuff like water walk, etc
    # - possibly send server imminent shutdown notice

    PACKET_BIN = Struct("<Q")
    VERIFY_WORLD_BIN = Struct("<I4f")

    def __init__(self, connection, packet):
        self.conn = connection
        self.packet = packet

    @db_connection
    def process(self):
        guid = self.PACKET_BIN.unpack(self.packet)[0]
        character_data = self._get_checked_character(guid)
        if character_data is None:
            LOG.warning("Account {} tried to illegally use character {}".format(
                self.conn.account.name, guid
            ))
            return self.conn.MAIN_ERROR_STATE, None

        # Now that we have the character data, spawn a new player object.
        self.conn.player = OBJECT_MANAGER.add_player(character_data)

        # Finally, send the packets necessary to let the client get in world.
        self.conn.send_packet(self._get_verify_login_packet())
        self.conn.send_packet(self._get_account_data_times_packet())
        self.conn.send_packet(self._get_tutorial_flags_packet())
        self.conn.send_packet(self._get_update_object_packet())

        return WorldConnectionState.IN_WORLD, None

    def _get_checked_character(self, guid):
        """ Get the character data associated to that GUID, but only if this
        character belongs to the connected account, else return None. """
        try:
            character = CharacterData.get(
                CharacterData.guid == guid
                and CharacterData.account == self.conn.account
            )
            return character
        except CharacterData.DoesNotExist:
            return None

    def _get_verify_login_packet(self):
        """ Send the unique (?) SMSG_LOGIN_VERIFY_WORLD packet. """
        response_data = self.VERIFY_WORLD_BIN.pack(
            self.conn.player.map_id,
            self.conn.player.position.x,
            self.conn.player.position.y,
            self.conn.player.position.z,
            self.conn.player.position.o
        )
        return WorldPacket(OpCode.SMSG_LOGIN_VERIFY_WORLD, response_data)

    DATA_TIMES_HEADER_BIN = Struct("<IBI")

    def _get_account_data_times_packet(self):
        """ Send this dummy packet to trigger account data sync. """
        header_data = self.DATA_TIMES_HEADER_BIN.pack(
            int(time.time()),
            1,
            AccountDataTypeMask.CHARACTER.value
        )

        dummy_account_data = AccountData()
        times = dummy_account_data.get_times(AccountDataTypeMask.CHARACTER)
        times_data = b"".join([int.to_bytes(t, 4, "little") for t in times])

        response_data = header_data + times_data
        return WorldPacket(OpCode.SMSG_ACCOUNT_DATA_TIMES, response_data)

    def _get_tutorial_flags_packet(self):
        """ I agree with myself that I do not want to support tutorials. """
        tutorial_data = int.to_bytes(0xFFFFFFFF, 4, "little") * 8
        return WorldPacket(OpCode.SMSG_TUTORIAL_FLAGS, tutorial_data)

    def _get_update_object_packet(self):
        """ Get the UpdateObjectPacket needed to spawn in world. """
        return PlayerSpawnPacket(self.conn.player)
