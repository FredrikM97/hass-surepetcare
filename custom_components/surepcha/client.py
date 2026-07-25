"""SurePetcareClient wrapper that runs chained follow-up commands concurrently."""

import asyncio
from typing import Union

from surepcio import SurePetcareClient as _SurePetcareClient
from surepcio.command import Command


class SurePetcareClient(_SurePetcareClient):
    """Execute list[Command] concurrently instead of one request at a time.

    The upstream client's api() awaits a list of chained commands
    sequentially. Household.get_pets()/get_devices() chain into exactly
    that - one refresh Command per pet/device - so a household with N pets
    and M devices costs N+M sequential round trips. Running them
    concurrently instead cuts that to roughly the slowest single call.
    """

    async def api(self, command: Union[Command, list[Command]]):
        if isinstance(command, list):
            return list(await asyncio.gather(*(self.api(cmd) for cmd in command)))
        return await super().api(command)
