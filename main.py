import time
from string import Template

import gns3fy

from config import *
from util import *


def make_config(router: Node, area: str = OSPF_AREA, ospf_process: int = OSPF_PROCESS) -> str:
    s = f"""###### config pour {router.name} ######
{main_menu}
#--
{get_extra_global_conf(router.name)}
"""
    if get_is_router_disabled(router.name):
        return "# configuration automatique desactivee par l'utilisateur"
    rid = get_router_id_overriden(router.name)
    if rid:
        router.router_id = rid
    s += Template(router_template).safe_substitute(ospf_process=ospf_process, router_id=rid)

    for interface in router.interfaces:
        extra_conf_int = get_extra_interface_conf(router.name, interface.get_name())
        if interface.lien.disable:
            continue  # on saute la config de l'interface
        if len(extra_conf_int) > 1 or interface.lien.has_extra_conf():
            s += f"""#--
# config custom du lien {interface.lien.get_name()}, partie globale pour le routeur
{interface.lien.extra_conf_router}
int {interface.get_name()}
# config custom du lien {interface.lien.get_name()}, partie specifique a cette interface
{extra_conf_int}
{interface.lien.extra_conf_interface}
"""
        if get_is_interface_disabled(router.name, interface.get_name()):
            continue
        s += Template(interface_base_template).safe_substitute(
            interface_name=interface.get_name(),
            reverse_interface_name=interface.reverse_int(),
            reverse_router_name=interface.reverse_router().name,
            ip4=interface.get_ip4(),
            ip6=interface.get_ip6()
        )
        if interface.reverse_router().router:
            s += Template(interface_routing_template).safe_substitute(ospf_process=ospf_process,
                                                                      area=area)

    s += f"""
end
###### fin de la config pour {router.name} ######
"""

    return s


def apply_config(router: Node, config: str):
    console = Console(router.console_host, router.console)

    console.write_cmd(b'\r')  # active la console
    console.write_cmd(b'end')
    console.write_cmd(b'configure terminal')
    for part in config.split('#--'):
        console.write_conf(part)
        time.sleep(0.1)


if __name__ == '__main__':
    gs = gns3fy.Gns3Connector("http://localhost:3080", user="admin")
    if GNS3_PROJECT_NAME != 'auto':
        project_id = gs.get_project(name=GNS3_PROJECT_NAME)['project_id']
    else:
        # sinon on récup le 1er projet ouvert dans GNS3 en ce moment
        project_id = list(filter(lambda p: p['status'] == 'opened', gs.get_projects()))[0]['project_id']
    project = gns3fy.Project(project_id=project_id, connector=gs)
    project.get()

    # énumération des noeuds du projet et initialisation des consoles
    mynodes = enumerate_nodes(gs, project_id)

    # énumération & résolution des liens puis assignation des réseaux
    liens = enumerate_links(gs, project_id, mynodes)

    print(make_config(mynodes.get_by_name('R5')))
    exit(0)

    # applique les configs sur tous les routeurs
    for node in mynodes.values():
        if node.router:
            cfg = make_config(node)  # génère la config
            # print(cfg)
            print(f"envoi de la configuration à {node.name} (router-id {node.router_id}) ... ", end="")
            apply_config(node, cfg)  # reconfigure le routeur Cisco
            print("fini !")

    # efface les dessins précédents
    project.get_drawings()
    delete_drawings(project)

    # partie qui fait le joli affichage dans GNS3
    # il faut qu'elle soit après la génération des configs car certaines valeurs 'custom' sont récupérées à ce moment
    display_subnets(project, liens)
    display_router_ids(project, mynodes.values())
