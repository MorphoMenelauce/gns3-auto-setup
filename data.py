from collections import namedtuple
from dataclasses import dataclass
from typing import List, Optional, Union

from gns3fy import Node, Link


@dataclass
class Router:
    name: str
    x: int
    y: int
    uid: str
    router_id: str

    # type: List[Interface]
    interfaces:list

    @staticmethod
    def from_node(node: Node, ri):
        return Router(name=node.name, x=node.x, y=node.y, uid=node.node_id, router_id=ri, interfaces=[])


class Routers(dict):
    # type: List[Router]
    def get_by_uid(self, uid: str) -> Router:
        for router in self.values():
            if router.uid == uid:
                return router

    def add(self, router: Router):
        self[router.name] = router

    def __getitem__(self, item) -> Router:
        return super().__getitem__(item)


@dataclass
class Lien:
    uid: str

    network4: str
    network6: str

    side_a: Router
    side_b: Router

    int_a: str
    int_b: str

    @property
    def interface_a(self):
        # type: () -> Interface
        return list(filter(lambda i: i.name == self.int_a, self.side_a.interfaces))[0]

    @property
    def interface_b(self):
        # type: () -> Interface
        return list(filter(lambda i: i.name == self.int_b, self.side_b.interfaces))[0]

    def __str__(self):
        return f"({self.side_a.name}) {self.int_a} <-> {self.int_b} ({self.side_b.name})"

SIDE_A = 'a'
SIDE_B = 'b'


@dataclass
class Interface:
    name: str
    lien: Union[Lien, None] = None  # si None, le lien n'est pas branché à un routeur
    side: str = 'u'  # 'a' ou 'b' ou 'u' si lien==None

    @property
    def peer(self) -> Router:
        if self.lien is not None:
            if self.side == 'a':
                return self.lien.side_b
            elif self.side == 'b':
                return self.lien.side_a
        return None

    @property
    def peer_int(self) -> str:
        if self.lien is not None:
            if self.side == 'a':
                return self.lien.int_b
            elif self.side == 'b':
                return self.lien.int_a
        return None

    @property
    def router(self) -> Router:
        if self.lien is not None:
            if self.side == 'b':
                return self.lien.side_b
            elif self.side == 'a':
                return self.lien.side_a
        return None

    def __str__(self):
        if self.lien is not None:
            return str(self.lien)
        return self.name



router = {
    'name': 'R5',
    # 'disable': False,
    'extra': '# rien',
    'router_id': '0.0.0.0',
    'interfaces': [
        {
            'name': 'f0/0',
            # 'disable': False,
            'extra': ' je suis {{router_id}}',
            'ip4': '10.0.0.1 255.255.0.0',
            'ip6': '2001:0::1/64',
        },
        {
            'name': 'f3/0',
            # 'disable': False,
            'extra': '#oui',
            'ip4': '10.2.0.2 255.255.0.0',
            'ip6': '2001:2::2/64',
        }
    ]
}
# on laisse l'utilisateur rajouter sa sauce au template -> on ne fournit pas le router-id
user_template = """
ipv6 unicast-routing
ip cef
ipv6 router ospf 1
    redistribute connected
    router-id {{router_id}}
  exit
router ospf 1
    redistribute connected subnets
    router-id {{router_id}}
  exit
{{extra}}
{% for interface in interfaces %}
int {{interface.name}}
    no shut
    ip address {{interface.ip4}}
    mpls ip
    ipv6 enable
    ipv6 address {{interface.ip6}}
    # extra
    {{interface.extra}}
  exit
{% endfor %}
"""

if __name__ == '__main__':
    from jinja2 import Template

    t = Template(user_template)
    v = Template(t.render(router))
    print(v.render(router))
