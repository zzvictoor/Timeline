"""Timeline base value objects."""

from math import ceil
import time

from Timeline.Utils.Crumbs.Items import Item


class Username(str):
    def __new__(cls, username, client):
        return str.__new__(cls, username)

    def __init__(self, username, client):
        self.u = username
        self.c = client

    @property
    def username(self):
        return self.u

    @property
    def name(self):
        return self.u

    @property
    def value(self):
        return self.u


class Password(str):
    def __new__(cls, password, client):
        return str.__new__(cls, password.upper())

    def __init__(self, password, client):
        self.p = password
        self.c = client

    @property
    def value(self):
        return self.p


class Nickname(str):
    def __new__(cls, nickname, client):
        return str.__new__(cls, nickname)

    def __init__(self, nickname, client):
        self.n = str(nickname).title()
        self.c = client

    def __str__(self):
        return self.n

    def __repr__(self):
        return self.n

    def _update(self, nickname):
        """Queue the DB update without turning a property setter into a generator."""
        deferred = self.c.db_nicknameUpdate(nickname)

        def apply_if_saved(saved):
            if saved:
                self.n = nickname
            return saved

        deferred.addCallback(apply_if_saved)
        return deferred

    @property
    def nickname(self):
        return self.n

    @nickname.setter
    def nickname(self, nickname):
        self._update(nickname)

    @property
    def value(self):
        return self.n

    @value.setter
    def value(self, nickname):
        self._update(nickname)


class EPFAgent(object):
    def __init__(self, epf, point, client):
        self.e = bool(epf)
        self.p, self.t = map(int, point.split("%"))
        self.c = client

    def __repr__(self):
        return "EPF:{}<{},{}>".format(self.e, self.p, self.t)

    def __int__(self):
        return self.p

    def __bool__(self):
        return self.e

    def __str__(self):
        return "%".join(map(str, [self.e, self.p, self.t]))


class Membership(object):
    def __init__(self, membership, client):
        expires = membership.expires
        redeemed = membership.redeemed_on
        self.mdays = (expires - redeemed).days if expires > expires.now() else 0
        self.enum = int(self.mdays > 0)
        if self.mdays == 7:
            self.enum = 2
        self.mrem = (expires - expires.now()).days if self.enum else 0

    def __repr__(self):
        return str(self.mdays)

    def __str__(self):
        return str(self.mdays)

    def __int__(self):
        return int(self.mdays)

    def __bool__(self):
        return self.mdays > 0


class Cache(object):
    def __init__(self, client):
        self.playerWidget = ""
        self.mapCategory = ""
        self.NX = ""
        self.igloo = ""
        self.GAS = ""


class Age(object):
    def __init__(self, created, client):
        self.age = int(time.mktime(created.timetuple()))
        self.c = client

    @property
    def days(self):
        return int(ceil((time.time() - self.age) / (60 * 60 * 24.0)))

    def __repr__(self):
        return str(self.days)

    def __str__(self):
        return str(self.days)

    def __int__(self):
        return self.days


class Coins(object):
    def __repr__(self):
        return str(self.coins)

    def __str__(self):
        return str(self.coins)

    def __int__(self):
        return int(self.coins)

    def __add__(self, amount):
        value = Coins(self.coins, None)
        value += amount
        return value

    def __iadd__(self, amount):
        if self.coins + amount < 1:
            return self
        self.coins += amount
        self.__update()
        return self

    def __sub__(self, amount):
        return self + (-amount)

    def __isub__(self, amount):
        self += -amount
        return self

    def __init__(self, coins, client):
        self.coins = int(coins)
        self.c = client

    def __update(self):
        if self.c is None:
            return
        self.c.dbpenguin.coins = self.coins
        self.c.dbpenguin.save()


class Inventory(list):
    _extend = True

    def __init__(self, penguin, *items):
        super(Inventory, self).__init__()
        self.penguin = penguin
        for item in items:
            self.append(item, False)

    def parseFromString(self, string, delimiter="%"):
        if string in (None, ""):
            return
        for item in str(string).split(delimiter):
            self.append(item, False)

    def __str__(self):
        return "%".join(map(str, self))

    def _addItem_(self, item, update=True):
        if self.penguin is None or not update:
            return
        self.penguin.dbpenguin.inventory = "%".join(map(str, self))
        self.penguin.dbpenguin.save()

    def itemsByType(self, item_type):
        if isinstance(item_type, type) and issubclass(item_type, Item):
            item_type = item_type.type
        return Inventory(None, *(item for item in self if item.type == item_type))

    def __contains__(self, item):
        if isinstance(item, int):
            return self.hasItem(item)
        if isinstance(item, Item):
            return self.hasItem(item.id)
        if isinstance(item, str):
            try:
                return self.hasItem(int(item))
            except ValueError:
                for existing in self:
                    if existing.__name__.lower() == item.lower().strip():
                        return True
        if isinstance(item, list):
            return all(value in self for value in item)
        return False

    def hasType(self, item_type):
        return any(item.type == item_type for item in self)

    def hasItem(self, item_id):
        return any(item.id == item_id for item in self)

    def append(self, item, update=True):
        if self.penguin is None:
            return super(Inventory, self).append(item)

        if not isinstance(item, Item):
            if isinstance(item, int):
                resolved = self.penguin.engine.itemCrumbs[item]
                if resolved is False:
                    return None
                return self.append(resolved, update)
            if isinstance(item, str):
                try:
                    return self.append(int(item), update)
                except ValueError:
                    resolved = self.penguin.engine.itemCrumbs[item]
                    if resolved is False:
                        return None
                    return self.append(resolved, update)
            return None

        if item in self:
            return None
        super(Inventory, self).append(item)
        self._addItem_(item, update)
        return item

    def insert(self, index, item):
        if isinstance(item, Item):
            super(Inventory, self).insert(index, item)

    def __add__(self, items):
        inventory = Inventory(None, *self)
        inventory += items
        return inventory

    def __iadd__(self, items):
        if isinstance(items, list):
            for item in items:
                self.append(item)
        else:
            self.append(items)
        return self
