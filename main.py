import json
import time
from socket import *
from copy import deepcopy
from ipaddress import IPv4Address
from typing import Set, Iterable

from gns3fy import gns3fy, Node, Link, Project

from config import config_custom
from data import *
from jinja2 import Template

MAGIC_SVG = '<!-- fait par le script -->'

def enumerate_routers(gs, project_id):
    routers = Routers()

    router_i = 1
    for node in gs.get_nodes(project_id):
        obj = Node(project_id=project_id, node_id=node['node_id'], connector=gs)
        obj.get()
        if obj.node_type == 'dynamips':
            routers.add(Router.from_node(obj, str(IPv4Address(router_i))))
            router_i += 1
    return routers


def enumerate_links(gs, project_id, routers: Routers)->List[Lien]:
    in4 = 2887680000
    liens = []
    for _link in gs.get_links(project_id):
        link = Link(connector=gs, project_id=project_id, link_id=_link['link_id'])
        link.get()

        router_side_a = routers.get_by_uid(link.nodes[0]['node_id'])
        router_side_b = routers.get_by_uid(link.nodes[1]['node_id'])

        if router_side_b is None:
            router_side_a.interfaces.append(Interface(name=link.nodes[0]['label']['text']))
            continue
        elif router_side_a is None:
            router_side_b.interfaces.append(Interface(name=link.nodes[1]['label']['text']))
            continue

        lien = Lien(
            uid=link.link_id,
            network6='2001:' + link.link_id.split('-')[3],
            network4=IPv4Address(in4),
            side_a=router_side_a, side_b=router_side_b,
            int_a=link.nodes[0]['label']['text'],
            int_b=link.nodes[1]['label']['text'],
        )
        in4 += 4
        # print("enumerating link " + str(lien))

        side_a_interface = Interface(name=link.nodes[0]['label']['text'], lien=lien, side=SIDE_A)
        side_b_interface = Interface(name=link.nodes[1]['label']['text'], lien=lien, side=SIDE_B)

        # relie les deux interfaces ensembles
        side_a_interface.lien = lien
        side_b_interface.lien = lien

        # attache l'interface au routeur
        router_side_a.interfaces.append(side_a_interface)
        router_side_b.interfaces.append(side_b_interface)

        liens.append(lien)
    for lien in liens:
        print(f'{lien.side_a.name}>    {lien.network4}    <{lien.side_b.name}')
        #print(f'{lien.interface_a.get_ip4()} {lien.side_a.name}>    {lien.network4}    <{lien.side_b.name} {lien.interface_b.get_ip4()}')
    return liens


def get_gns_conf():
    gs = gns3fy.Gns3Connector("http://localhost:3080", user="admin")
    project_id = list(filter(lambda p: p['status'] == 'opened', gs.get_projects()))[0]['project_id']
    project = gns3fy.Project(project_id=project_id, connector=gs)
    project.get()

    routers = enumerate_routers(gs, project_id)
    liens = enumerate_links(gs, project_id, routers)
    return routers, gs, project_id, liens


def show_topology(routers: Routers):
    for router in routers.values():
        print(f"routeur {router.name}")
        for itf in router.interfaces:
            print(
                f" *   {itf.name} -> {itf.peer.name if itf.peer is not None else 'client'}: {itf.peer_int if itf.peer is not None else ''}")


def gen_tree(router: Router) -> dict:
    ifs = []
    for int in router.interfaces:
        interface: Interface = int
        if interface.peer is not None:  # un routeur de l'autre côté
            ifs.append({
                'name': interface.name,
                'lien': interface.lien.name,
                'ip_network4': interface.get_ip4(),
                'ip_network6': interface.lien.network6,
                'ip_end6': interface.end6(),
            })
        else:
            ifs.append({
                'name': interface.name,
                'lien': 'edge',
                'ip_network4': 'configurez manuellement',
                'ip_network6': 'configurez manuellement',
                'ip_end6': '1',
            })
    return {
        'name': router.name,
        'router_id': router.router_id,
        'interfaces': ifs
    }


def find(liste: list, k, v):
    try:
        return list(filter(lambda e: e[k] == v, liste))[0]
    except IndexError:
        print(f"['{k}']={v} non trouvé !\n il vous manque sûrement la classe {v}")
        exit(1)


def r2(classnames: Set[str]) -> Set[str]:
    """
    Normalement il peut pas faire de RecursionError
    :param classnames: la liste des classes à étendre récursivement
    :return: toutes les classes découvertes+initiales
    """
    if len(classnames) == 0:
        return set()
    discovered = set()
    for classe in config_custom['classes']:
        if classe['name'] in classnames:
            discovered.update(safe_get_value(classe, [], 'classes'))
    initial = set(classnames)
    nouveaux = discovered - initial
    if len(discovered) == 0 or len(nouveaux) == 0:
        return initial | discovered
    missing = r2(nouveaux)
    return initial | discovered | missing


def resolve_classes(classe_names: List[str], type) -> List[dict]:
    all_class_names = r2(set(classe_names))
    l = []
    for classe_name in all_class_names:
        classe_obj: dict = find(config_custom['classes'], 'name', classe_name)
        if classe_obj['type'] == type:
            classe_obj = deepcopy(classe_obj)
            classe_obj.pop('classes', None)
            l.append(classe_obj)
    return l


def safe_get_value(data: dict, default, *args):
    try:
        obj = data
        for path in args:
            obj = obj[path]
        return obj
    except (KeyError, TypeError):
        return default
    except Exception as e:
        raise e
        return default


def apply_values(classes: List[dict], obj: dict):
    # rajoute les variables définies dans les classes
    for classe in classes:
        obj.update(safe_get_value(classe, {}, 'values'))


def add_templates(classes: List[dict]) -> str:
    t = ''
    for classe in classes:
        t += safe_get_value(classe, '', 'template')
    return t


def resolve_link_config(router_a_name: str, router_b_name: str) -> dict:
    try:
        for link in config_custom['links']:
            if link['name'] == (router_a_name + '<-->' + router_b_name) or link['name'] == (
                    router_b_name + '<-->' + router_a_name):
                return link
        return None
    except (KeyError, AttributeError):
        return None


def resolve_router_config(router: Router):
    """
    construit la config et fait le templating des templates (sans appliquer les valeurs)
    :param router:
    :return:
    """
    conf = gen_tree(router)
    template = safe_get_value(config_custom, '', 'templates', 'router')
    cc = safe_get_value(config_custom, {}, 'routers', router.name)
    classes = resolve_classes(safe_get_value(cc, [], 'classes') + config_custom['default_router_classes'], 'router')
    apply_values(classes, conf)

    if cc.get('values'):
        conf.update(cc['values'])
    conf['resolved_classes'] = classes

    conf['interface_classes'] = []
    for classe in filter(lambda c: c.get('interface_classes'), classes):
        conf['interface_classes'].extend(classe['interface_classes'])
    conf['disable'] = safe_get_value(cc, False, 'disable')

    for interface in router.interfaces:
        int_conf = find(conf['interfaces'], 'name', interface.name)  # la config auto-généré
        user_def_interface = safe_get_value(cc, {}, 'interfaces', interface.name)  # la config utilisateur
        int_conf['disable'] = safe_get_value(user_def_interface, False, 'disable')
        if_classes = resolve_classes(
            safe_get_value(user_def_interface, [], 'classes')
            + config_custom['default_interface_classes']
            + conf['interface_classes'] if interface.peer is not None else [] # fait en sorte
            # de ne pas configurer de protocole de routage sur une interface de bordure
            # les interfaces externes doivent être config à la main
            , 'interface')
        apply_values(if_classes, int_conf)
        if user_def_interface.get('values'):
            int_conf.update(user_def_interface['values'])
        int_conf['resolved_classes'] = if_classes
        int_conf['template'] = safe_get_value(config_custom, '', 'templates', 'interface')
        int_conf['interface_template'] = safe_get_value(user_def_interface, '', 'template')

        if interface.peer is not None:
            lien_custom = resolve_link_config(router.name, interface.peer.name)
        else:
            lien_custom = None
        if lien_custom is not None:  # ajoute des configurations personalisées à l'interface depuis la config des liens
            link_classes = resolve_classes(safe_get_value(lien_custom, [], 'interface_classes'), 'interface')
            apply_values(link_classes, int_conf)
            int_conf['resolved_classes'] += link_classes
            router_classes = resolve_classes(safe_get_value(lien_custom, [], 'router_classes'), 'router')
            apply_values(router_classes, conf)
            conf['resolved_classes'] += router_classes
            int_conf['interface_template'] += safe_get_value(lien_custom, '', 'template')

            # re-mapping
            interface.lien.network6 = int_conf['ip_network6']
            #interface.lien.network4 = int_conf['ip_network4']
        conf['template'] = '\n' + safe_get_value(cc, '', 'template') + add_templates(classes)
    conf['template'] = template

    # re-mapping de la config utilisateur, pour les dessins GNS3
    router.router_id = conf['router_id']

    return conf
    # except:
    #    print("ATTENTION: la configuration")
    #    return conf


def generate_conf(conf: dict) -> str:
    rendered_interfaces = []
    for interface in conf['interfaces']:
        pass1 = Template(interface['template']).render(interface=interface, router=conf)
        rendered_interfaces.append(Template(pass1).render(interface=interface, router=conf))

    t1 = Template(conf['template']).render(router=conf, rendered_interfaces=rendered_interfaces)
    return Template(t1).render(router=conf, ospf_process=1)


class Console:
    sock: socket

    def __init__(self, console_host, console_port):
        self.sock = socket()
        try:
            self.sock.connect((console_host, console_port))
        except ConnectionRefusedError:
            print("Vous devez lancer le projet GNS3 pour configurer les routeurs")
            exit(0)

    def write_conf(self, text: str):
        # on remplace \n par \r car la console Cisco attend \r comme saut de ligne
        self.write_cmd(b'')
        self.write_cmd(b'configure terminal')
        self.sock.send(text.replace('\n', '\r').encode('utf-8'))
        self.write_cmd(b'end')

    def write_cmd(self, cmd: bytes):
        self.sock.send(cmd + b'\r')

    @staticmethod
    def from_router(router: Router):
        return Console(console_host=router.console_host, console_port=router.console_port)


def configure_router(router: Router) -> Console:
    conf = generate_conf(resolve_router_config(router))
    console = Console.from_router(router)
    print(f'configuration de  {router.name}')
    for partie in conf.split('#--'):
        console.write_conf(partie)
        time.sleep(0.5)
        print('.',end='')
    time.sleep(1)
    print(f"{router.name} configuré !")
    return console

def delete_drawings(project: Project):
    if project.drawings is not None:
        for draw in project.drawings:
            s = draw['svg']
            if s.split('>', 1)[1].startswith(MAGIC_SVG):  # or not draw['locked']:
                project.update_drawing(drawing_id=draw['drawing_id'], locked=False)
                project.delete_drawing(drawing_id=draw['drawing_id'])

def display_tracked_subnets(project: Project, liens:List[Lien]):
    # affiche les subnets entre routeurs
    for lien in liens:
        text = f"{lien.network4}/30\n{lien.network6}::"
        x = (lien.side_a.x + lien.side_b.x) // 2 - 25
        y = (lien.side_a.y + lien.side_b.y) // 2
        project.create_drawing(
            svg=f'<svg width="120" height="40">{MAGIC_SVG}<rect width="120" height="40" fill="#ffffff" fill-opacity="1.0" stroke-width="2" stroke="#000000"/></svg>',
            x=x, y=y, z=1, locked=True)
        project.create_drawing(
            svg=f'<svg width="39" height="30">{MAGIC_SVG}<text font-family="TypeWriter" font-size="10.0" font-weight="bold" fill="#346c59" stroke="#afafe1" stroke-width="100" fill-opacity="1.0">{text}\n</text>'
                + '</svg>',
            x=x, y=y, z=100, locked=True)

def display_router_ids(project: Project, routers: Routers):
    # affiche les router-ids
    for node in routers.values():
        x = node.x
        y = node.y + 10
        project.create_drawing(
            svg=f'<svg width="60" height="15">{MAGIC_SVG}<rect width="60" height="15" fill="#ffffff" fill-opacity="1.0"/></svg>',
            x=x, y=y, locked=True)
        project.create_drawing(
            svg=f'<svg width="100" height="15">{MAGIC_SVG}<text>{node.router_id}</text></svg>',
            x=x, y=y - 4, locked=True)


if __name__ == '__main__':
    routers, gs, project_id, liens = get_gns_conf()
    show_topology(routers)

    for router in routers.values():
        # print(generate_conf(resolve_router_config(router)))
        configure_router(router)

    project = gns3fy.Project(project_id=project_id, connector=gs)
    project.get()
    delete_drawings(project)
    display_tracked_subnets(project, liens)
    display_router_ids(project,routers)
