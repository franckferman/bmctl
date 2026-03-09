import os
import json
import argparse
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from collections import defaultdict
import datetime
import csv
import pandas as pd

# ==============================================================================
# MODELES DE DONNEES
# ==============================================================================

class BookmarkNode:
    """Represente un favori unique."""
    def __init__(self, original_url, title, path, tags, date_added):
        self.original_url = original_url
        self.title = title if title else "[SANS TITRE]"
        self.path = path if path else "Racine"
        self.tags = tags
        self.date_added = date_added
        
        # Proprietes calculees
        self.clean_url = UrlNormalizer.normalize(original_url)

    def __repr__(self):
        return f"<BookmarkNode: {self.title} ({self.clean_url})>"

# ==============================================================================
# UTILITAIRES
# ==============================================================================

class UrlNormalizer:
    """Classe utilitaire pour standardiser les URLs."""
    
    @staticmethod
    def normalize(url: str) -> str:
        """Nettoie l'URL pour detecter les vrais doublons."""
        try:
            parsed = urlparse(url)
            query_params = parse_qsl(parsed.query)
            clean_params = [(k, v) for k, v in query_params if not k.lower().startswith('utm_')]
            new_query = urlencode(clean_params)

            netloc = parsed.netloc.lower()
            if netloc.startswith('www.'):
                netloc = netloc[4:]

            path = parsed.path
            if path.endswith('/'):
                path = path[:-1]

            scheme = 'https' if parsed.scheme in ['http', 'https'] else parsed.scheme
            
            return urlunparse((scheme, netloc, path, parsed.params, new_query, parsed.fragment))
        except Exception:
            return url.lower().strip()

# ==============================================================================
# GESTIONNAIRES DE BASES DE DONNEES
# ==============================================================================

class BookmarkDatabase:
    """Stocke et indexe une collection de favoris."""
    
    def __init__(self):
        self.nodes = []
        self.url_map = defaultdict(list)
        
        self.stats = {
            'total_bookmarks': 0,
            'total_folders': 0,
        }

    # Root identifiers that should NOT become path components
    _ROOT_IDS = {
        'placesRoot', 'toolbarFolder', 'bookmarksMenuFolder',
        'unfiledBookmarksFolder', 'mobileFolder', 'tagsFolder'
    }
    # Firefox export format can use typeCode (int) OR type (string) depending on version
    _TYPE_FOLDER_STR = 'text/x-moz-place-container'
    _TYPE_BOOKMARK_STR = 'text/x-moz-place'

    def load_firefox_json(self, filepath: str):
        """Charge un fichier d'export JSON de Firefox (tous formats)."""
        with open(filepath, 'r', encoding='utf-8') as f:
            root_json = json.load(f)
        # folder_order tracks first-encounter DFS order for dashboard widget ordering
        self.folder_order = []
        self._seen_folder_paths = set()
        self._process_node(root_json, "")

    @staticmethod
    def _is_folder(node: dict) -> bool:
        """Detecte un noeud dossier, compatible avec tous les formats d'export Firefox."""
        tc = node.get('typeCode')
        if tc is not None:
            return tc == 2
        t = node.get('type', '')
        return t == BookmarkDatabase._TYPE_FOLDER_STR or (
            'children' in node and not node.get('uri')
        )

    @staticmethod
    def _is_bookmark(node: dict) -> bool:
        """Detecte un noeud signet, compatible avec tous les formats d'export Firefox."""
        tc = node.get('typeCode')
        if tc is not None:
            return tc == 1
        t = node.get('type', '')
        if t == BookmarkDatabase._TYPE_BOOKMARK_STR:
            return True
        # Fallback: has a uri and no children
        return bool(node.get('uri')) and 'children' not in node

    def _process_node(self, node: dict, current_path: str):
        """Parcourt recursivement l'arbre JSON, format-agnostique."""
        if not isinstance(node, dict):
            return

        if self._is_folder(node):
            self.stats['total_folders'] += 1
            node_title = node.get('title', '').strip()
            node_root  = node.get('root', '')
            node_guid  = node.get('guid', '')

            # Skip structural root containers - they are invisible in the sidebar
            is_root_container = (
                node_root in self._ROOT_IDS
                or node_guid in self._ROOT_IDS
                or node_title in ('', 'root')
            )

            if is_root_container:
                new_path = current_path
            else:
                new_path = f"{current_path} > {node_title}" if current_path else node_title

            # Track DFS encounter order for dashboard widget ordering
            if new_path and new_path not in self._seen_folder_paths:
                self._seen_folder_paths.add(new_path)
                self.folder_order.append(new_path)

            if 'children' in node:
                for child in node['children']:
                    self._process_node(child, new_path)

        elif self._is_bookmark(node):
            url = node.get('uri', '')
            if not url or url.startswith('javascript:') or url.startswith('place:'):
                return

            bookmark = BookmarkNode(
                original_url=url,
                title=node.get('title', '').strip(),
                path=current_path if current_path else 'Racine',
                tags=node.get('tags', ''),
                date_added=node.get('dateAdded', 0)
            )
            self._add_bookmark(bookmark)

    def _add_bookmark(self, bookmark: BookmarkNode):
        """Ajoute un favori dans la base et met a jour les stats."""
        self.nodes.append(bookmark)
        self.url_map[bookmark.clean_url].append(bookmark)
        
        self.stats['total_bookmarks'] += 1

    def get_unique_urls(self) -> set:
        return set(self.url_map.keys())

    def get_duplicates(self) -> list:
        return [(url, occs) for url, occs in self.url_map.items() if len(occs) > 1]


# ==============================================================================
# AUDITEUR ET COMPARATEUR
# ==============================================================================

class BookmarkAuditor:
    
    def __init__(self, db: BookmarkDatabase):
        self.db = db

    def print_report(self, show_top=10, show_short=False, show_tree=False):
        unique_urls = len(self.db.url_map)
        duplicates_count = self.db.stats['total_bookmarks'] - unique_urls
        perc_dup = (duplicates_count / self.db.stats['total_bookmarks'] * 100) if self.db.stats['total_bookmarks'] > 0 else 0
        
        print("\n" + "="*70)
        print("               RAPPORT D'AUDIT GLOBAL")
        print("="*70)
        print(f" Total des favoris trouves    : {self.db.stats['total_bookmarks']}")
        print(f" Dossiers parcourus           : {self.db.stats['total_folders']}")
        print(f" Liens uniques                : {unique_urls}")
        print(f" Doublons detectes            : {duplicates_count} ({perc_dup:.1f}%)")
        print("="*70)

        if show_tree:
            self.print_tree()
            return
        
        if show_short:
            return
            
        doublons = self.db.get_duplicates()
        doublons_tries = sorted(doublons, key=lambda x: len(x[1]), reverse=True)
        
        if doublons_tries:
            print(f"\n[!] Top {show_top} des liens les plus dupliques :")
            for clean_url, occurrences in doublons_tries[:show_top]:
                print(f"\n  - {occurrences[0].title[:100]}")
                print(f"    URL : {clean_url}")
                print(f"    Present {len(occurrences)} fois :")
                
                paths_seen = set()
                for occ in occurrences:
                    location = occ.path
                    tags_info = f" [Tags: {occ.tags}]" if occ.tags else ""
                    if (location, tags_info) not in paths_seen:
                        print(f"      * Dossier : {location}{tags_info}")
                        paths_seen.add((location, tags_info))

    def print_tree(self):
        """
        Affiche la hierarchie de dossiers TELLE QUE LUE depuis le JSON Firefox.
        Utile pour diagnostiquer si des dossiers sont au mauvais niveau.
        
        Usage: python bookmark_toolkit.py audit -i fichier.json --show-tree
        """
        # Count bookmarks per folder path
        folder_counts = defaultdict(int)
        for node in self.db.nodes:
            folder_counts[node.path] += 1

        folder_order = getattr(self.db, 'folder_order', sorted(folder_counts.keys()))

        print("\n" + "="*70)
        print("    ARBRE DE DOSSIERS (ordre de parcours Firefox)")
        print("    Verifiez que vos sous-dossiers ont bien leur parent.")
        print("="*70)

        for path in folder_order:
            depth = path.count(' > ')
            indent = '  ' * depth
            leaf = path.split(' > ')[-1]
            count = folder_counts.get(path, 0)
            marker = '+--' if depth > 0 else '|  '
            print(f"  {indent}{marker} [{count:4d}]  {leaf}")
            if depth == 0 and count == 0:
                # Top-level folder with 0 direct bookmarks - probably a container
                pass

        print("="*70)
        print(f"  Total dossiers affiches : {len(folder_order)}")
        print()
        print("  Si 'Business' apparait sans indentation alors qu'il devrait etre")
        print("  sous 'Blogs & Press', c'est que dans Firefox il est bien au niveau")
        print("  racine - le dashboard est correct. Reorganisez dans Firefox d'abord.")


class BookmarkComparator:
    
    @staticmethod
    def compare(db_old: BookmarkDatabase, db_new: BookmarkDatabase, show_full=False, show_short=False):
        old_urls = db_old.get_unique_urls()
        new_urls = db_new.get_unique_urls()

        added = new_urls - old_urls
        removed = old_urls - new_urls
        
        added_nodes = [db_new.url_map[url][0] for url in added]
        removed_nodes = [db_old.url_map[url][0] for url in removed]

        print("\n" + "="*70)
        print("                 RAPPORT DE COMPARAISON")
        print("="*70)
        print(f" Favoris uniques V1 (Ancien)  : {len(old_urls)}")
        print(f" Favoris uniques V2 (Nouveau) : {len(new_urls)}")
        print(f" Delta net                    : {len(new_urls) - len(old_urls)}")
        print("="*70)
        print(f" [+] Nouveaux favoris ajoutes   : {len(added_nodes)}")
        print(f" [-] Anciens favoris supprimes  : {len(removed_nodes)}")
        print("="*70)

        if show_short:
            return

        limit = None if show_full else 15

        if added_nodes:
            title = "[+] LISTE COMPLETE DES NOUVELLES ENTREES :" if show_full else f"\n[+] APERCU DES NOUVELLES ENTREES (Max {limit}) :"
            print(title)
            display_nodes = added_nodes if show_full else added_nodes[:limit]
            for node in display_nodes:
                print(f"  + {node.title[:60].ljust(60)} (Dossier: {node.path})")
                print(f"    {node.original_url}")
            if not show_full and len(added_nodes) > limit:
                print(f"  ... et {len(added_nodes) - limit} autres.")

        if removed_nodes:
            title = "[-] LISTE COMPLETE DES ENTREES DISPARUES :" if show_full else f"\n[-] APERCU DES ENTREES DISPARUES (Max {limit}) :"
            print(title)
            display_nodes = removed_nodes if show_full else removed_nodes[:limit]
            for node in display_nodes:
                print(f"  - {node.title[:60].ljust(60)} (Ancien Dossier: {node.path})")
            if not show_full and len(removed_nodes) > limit:
                print(f"  ... et {len(removed_nodes) - limit} autres.")

class BookmarkMerger:
    
    @staticmethod
    def merge(db_base: BookmarkDatabase, db_new: BookmarkDatabase, no_confirm: bool, output_path: str):
        all_urls = db_base.get_unique_urls().union(db_new.get_unique_urls())
        final_nodes = []
        
        print("\n[*] Lancement du processus de fusion...")
        stats_auto_resolved = 0
        stats_manual_resolved = 0
        
        for url in all_urls:
            nodes_base = db_base.url_map.get(url, [])
            nodes_new = db_new.url_map.get(url, [])
            all_node_instances = nodes_base + nodes_new
            
            if not all_node_instances:
                continue

            unique_paths = list(set([n.path for n in all_node_instances]))
            if len(unique_paths) == 1:
                best_node = sorted(all_node_instances, key=lambda x: x.date_added, reverse=True)[0]
                BookmarkMerger._merge_tags(best_node, all_node_instances)
                final_nodes.append(best_node)
                stats_auto_resolved += 1
                continue
                
            if no_confirm:
                best_node = sorted(all_node_instances, key=lambda x: x.date_added, reverse=True)[0]
                BookmarkMerger._merge_tags(best_node, all_node_instances)
                final_nodes.append(best_node)
                stats_auto_resolved += 1
            else:
                best_node = BookmarkMerger._interactive_resolve(url, all_node_instances)
                BookmarkMerger._merge_tags(best_node, all_node_instances)
                final_nodes.append(best_node)
                stats_manual_resolved += 1

        print("\n" + "="*70)
        print("                     BILAN DE FUSION")
        print("="*70)
        print(f" Favoris uniques conserves   : {len(final_nodes)}")
        print(f" Conflits resolus auto       : {stats_auto_resolved}")
        print(f" Conflits resolus manuellement: {stats_manual_resolved}")
        print("="*70)
        
        BookmarkMerger._export_html(final_nodes, output_path)

    @staticmethod
    def _merge_tags(target_node, source_nodes):
        all_tags = set()
        for node in source_nodes:
            if node.tags:
                all_tags.update(node.tags.split(','))
        target_node.tags = ",".join(filter(None, all_tags))

    @staticmethod
    def _interactive_resolve(url, nodes):
        print(f"\n[?] CONFLIT DE DOSSIER DETECTE POUR :")
        print(f"    - URL : {url}")
        print(f"    - Titre : {nodes[0].title}")
        print("    Dans quels dossiers souhaitez-vous le conserver ?")
        
        unique_nodes_by_path = {}
        for n in nodes:
            if n.path not in unique_nodes_by_path:
                unique_nodes_by_path[n.path] = n
                
        choices = list(unique_nodes_by_path.values())
        
        for i, node in enumerate(choices, 1):
            print(f"      {i}) [Garder] -> {node.path}")
            
        print(f"      {len(choices) + 1}) Ignorer / Garder la version avec la date la plus recente")
        
        while True:
            try:
                choix = input("    Votre choix (1, 2...) : ")
                if choix == str(len(choices) + 1):
                    return sorted(nodes, key=lambda x: x.date_added, reverse=True)[0]
                
                idx = int(choix) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
                print("Choix invalide.")
            except ValueError:
                print("Veuillez entrer un chiffre.")

    @staticmethod
    def _export_html(nodes, output_path):
        print(f"[*] Generation du standard HTML : {output_path}")
        
        folders = defaultdict(list)
        for node in nodes:
            folders[node.path].append(node)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('<!DOCTYPE NETSCAPE-Bookmark-file-1>\n')
            f.write('<!-- This is an automatically generated file. -->\n')
            f.write('<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n')
            f.write('<TITLE>Bookmarks</TITLE>\n')
            f.write('<H1>Bookmarks Menu</H1>\n')
            f.write('<DL><p>\n')
            
            for path, folder_nodes in folders.items():
                f.write(f'    <DT><H3>{path}</H3>\n')
                f.write('    <DL><p>\n')
                for node in folder_nodes:
                    tag_attr = f' TAGS="{node.tags}"' if node.tags else ''
                    f.write(f'        <DT><A HREF="{node.original_url}" ADD_DATE="{int(node.date_added / 1000000)}"{tag_attr}>{node.title}</A>\n')
                f.write('    </DL><p>\n')
                
            f.write('</DL><p>\n')


# ==============================================================================
# DASHBOARD GENERATOR
# ==============================================================================

class BookmarkDashboardGen:
    """Genere un dashboard HTML interactif (bmctl dashboard)."""
    
    @staticmethod
    def generate(db: BookmarkDatabase, output_path: str):
        print(f"[*] Generation du dashboard bmctl : {output_path}")
        
        # Iterate db.nodes directly to preserve original Firefox tree traversal order
        js_data = []
        for n in db.nodes:
            js_data.append({
                "title": n.title,
                "url": n.original_url,
                "folder": n.path,
                "tags": n.tags,
                "date": BookmarkExporter._microsecs_to_datetime(n.date_added)
            })

        # folder_order = DFS traversal order from Firefox tree (set by load_firefox_json)
        folder_order = getattr(db, 'folder_order', [])

        def _safe_json(obj):
            """
            json.dumps safe for inline HTML script tag injection.
            If a title/URL contains '</script>', the browser HTML parser closes
            the tag early - rawBookmarks assignment is never completed, blank page.
            Fix: replace '</' with '<\\/' (backslash-slash). Valid per JSON spec
            (\\/ is an allowed escape for forward-slash) and opaque to HTML parser.
            """
            raw = json.dumps(obj, ensure_ascii=False)
            # Use str.replace with explicit 4-char replacement: < \ /
            return raw.replace('</', '<' + '\\' + '/')

        folder_order_json = _safe_json(folder_order)
        js_data_json = _safe_json(js_data)
        
        html = f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>bmctl - Bookmark Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        
        :root {{
            --bg-base: #000000;
            --bg-surface: #0a0a0a;
            --bg-card: #121212;
            --bg-card-hover: #1a1a1a;
            --border-subtle: #222222;
            --border-active: #333333;
            --text-primary: #ffffff;
            --text-secondary: #a0a0a0;
            --text-muted: #666666;
            --accent-brand: #0066cc;
            --accent-glow: rgba(0, 102, 204, 0.3);
            --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --border-radius-sm: 4px;
            --border-radius-md: 8px;
            --border-radius-lg: 12px;
            --sidebar-width: 260px;
        }}
        
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            background-color: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-ui);
            line-height: 1.5;
            display: flex;
            height: 100vh;
            overflow: hidden;
            font-size: 14px;
        }}

        .sidebar {{
            width: var(--sidebar-width);
            background-color: var(--bg-surface);
            border-right: 1px solid var(--border-subtle);
            display: flex;
            flex-direction: column;
            height: 100vh;
            flex-shrink: 0;
            z-index: 10;
        }}

        .brand {{
            padding: 24px 20px;
            display: flex;
            align-items: center;
            gap: 12px;
            border-bottom: 1px solid var(--border-subtle);
        }}
        .brand i {{ font-size: 1.5rem; color: var(--accent-brand); }}
        .brand h1 {{ font-size: 1.1rem; font-weight: 600; letter-spacing: -0.5px; }}
        .brand span {{ font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; margin-left: auto; }}

        .nav-section-title {{
            padding: 20px 20px 8px;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .folder-tree {{
            flex: 1;
            overflow-y: auto;
            padding: 0 12px 20px;
        }}
        .folder-tree::-webkit-scrollbar {{ width: 4px; }}
        .folder-tree::-webkit-scrollbar-thumb {{ background: var(--border-active); }}

        .folder-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            color: var(--text-secondary);
            border-radius: var(--border-radius-sm);
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 2px;
            text-decoration: none;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 0.9rem;
        }}
        .folder-item:hover {{ background-color: var(--bg-card); color: var(--text-primary); }}
        .folder-item.active {{ background-color: rgba(0, 102, 204, 0.1); color: var(--accent-brand); }}
        .folder-item.active i.fa-folder {{ color: var(--accent-brand); }}
        
        .folder-node {{
            margin-left: 12px;
            border-left: 1px solid rgba(255,255,255,0.05);
            display: none;
        }}
        .folder-node.root-node {{
            margin-left: 0;
            border-left: none;
            display: block;
        }}
        .folder-node.expanded {{
            display: block;
        }}
        
        .folder-toggle {{
            cursor: pointer;
            width: 16px;
            text-align: center;
            font-size: 0.75rem;
            color: var(--text-muted);
            transition: transform 0.2s;
        }}
        .folder-item i.fa-folder, .folder-item i.fa-folder-open {{ color: var(--text-muted); font-size: 0.85rem; }}

        .main-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }}

        .topbar {{
            height: 70px;
            padding: 0 32px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid var(--border-subtle);
            background-color: var(--bg-surface);
        }}

        .search-wrapper {{
            position: relative;
            width: 400px;
        }}
        .search-wrapper i {{
            position: absolute;
            left: 14px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
        }}
        .search-input {{
            width: 100%;
            background-color: var(--bg-base);
            border: 1px solid var(--border-subtle);
            color: var(--text-primary);
            padding: 10px 16px 10px 40px;
            border-radius: 20px;
            font-size: 0.9rem;
            transition: all 0.2s;
            font-family: var(--font-ui);
        }}
        .search-input:focus {{
            outline: none;
            border-color: var(--accent-brand);
            box-shadow: 0 0 0 2px var(--accent-glow);
            background-color: var(--bg-card);
        }}

        .view-controls {{
            display: flex;
            gap: 8px;
            background-color: var(--bg-base);
            padding: 4px;
            border-radius: var(--border-radius-md);
            border: 1px solid var(--border-subtle);
        }}
        .btn-view {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 6px 10px;
            border-radius: var(--border-radius-sm);
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn-view:hover {{ color: var(--text-primary); }}
        .btn-view.active {{ background-color: var(--bg-card-hover); color: var(--text-primary); }}

        .workspace {{
            flex: 1;
            overflow-y: auto;
            padding: 32px;
            background-color: var(--bg-base);
        }}
        .workspace::-webkit-scrollbar {{ width: 8px; }}
        .workspace::-webkit-scrollbar-thumb {{ background: var(--border-active); border-radius: 4px; border: 2px solid var(--bg-base); }}

        .folder-header {{ margin-bottom: 24px; }}
        .folder-header h2 {{ font-size: 1.5rem; font-weight: 500; letter-spacing: -0.5px; display: flex; align-items: center; gap: 12px; }}
        .folder-stats {{ font-size: 0.85rem; color: var(--text-muted); margin-top: 8px; }}

        .dashboard-container {{
            column-count: 3;
            column-gap: 24px;
        }}
        @media (max-width: 1400px) {{ .dashboard-container {{ column-count: 2; }} }}
        @media (max-width: 900px) {{ .dashboard-container {{ column-count: 1; }} }}

        .widget-group {{
            break-inside: avoid;
            background-color: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--border-radius-md);
            margin-bottom: 24px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .widget-header {{
            background-color: var(--bg-card);
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-subtle);
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .widget-header i {{ color: var(--accent-brand); font-size: 0.8rem; }}
        .widget-content {{ padding: 8px; }}
        
        .list-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px;
            border-radius: var(--border-radius-sm);
            text-decoration: none;
            transition: background 0.2s;
        }}
        .list-item:hover {{ background-color: var(--bg-card-hover); }}
        .list-item-favicon {{ 
            width: 16px; height: 16px; 
            background-color: var(--border-subtle);
            border-radius: 3px;
            display: flex; align-items: center; justify-content: center;
            font-size: 10px; color: var(--text-muted);
            flex-shrink: 0;
        }}
        .list-item-details {{ flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }}
        .list-item-title {{ color: #e2e8f0; font-size: 0.9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .list-item:hover .list-item-title {{ color: var(--accent-brand); }}
        .list-item-url {{ color: var(--text-muted); font-size: 0.75rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 16px;
        }}
        .bmc-card {{
            background-color: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--border-radius-md);
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            transition: all 0.2s;
            text-decoration: none;
            height: 100%;
        }}
        .bmc-card:hover {{
            background-color: var(--bg-card);
            border-color: var(--border-active);
            transform: translateY(-2px);
        }}
        .bmc-header {{ display: flex; align-items: flex-start; gap: 12px; }}
        .bmc-icon {{ 
            width: 32px; height: 32px; 
            background: linear-gradient(135deg, var(--bg-card-hover), var(--border-subtle));
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            color: var(--accent-brand);
            flex-shrink: 0;
        }}
        .bmc-info {{ flex: 1; min-width: 0; }}
        .bmc-title {{ color: var(--text-primary); font-size: 0.95rem; font-weight: 500; margin-bottom: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .bmc-folder {{ font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono); }}
        .bmc-url {{ color: var(--text-secondary); font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-top: 8px; border-top: 1px dashed var(--border-subtle); }}
        .bmc-tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }}
        .bmc-tag {{ background: var(--bg-base); border: 1px solid var(--border-subtle); color: var(--text-secondary); padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; }}

        .table-view {{ width: 100%; border-collapse: collapse; }}
        .table-view th {{ text-align: left; padding: 12px 16px; color: var(--text-muted); font-weight: 500; font-size: 0.8rem; border-bottom: 1px solid var(--border-active); background: var(--bg-surface); position: sticky; top: 0; z-index: 1; }}
        .table-view td {{ padding: 12px 16px; border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); font-size: 0.85rem; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .table-view tr:hover td {{ background-color: var(--bg-surface); }}
        .table-view a.tbl-title {{ color: var(--text-primary); text-decoration: none; font-weight: 500; }}
        .table-view a.tbl-title:hover {{ color: var(--accent-brand); text-decoration: underline; }}
        .table-view .tbl-url {{ color: var(--text-muted); font-family: var(--font-mono); font-size: 0.75rem; }}
        
        .empty-state {{ padding: 60px 20px; text-align: center; color: var(--text-muted); }}
        .empty-state i {{ font-size: 3rem; margin-bottom: 16px; opacity: 0.5; }}
    </style>
</head>
<body>

    <aside class="sidebar">
        <div class="brand">
            <i class="fa-solid fa-terminal"></i>
            <h1>bmctl</h1>
            <span>v1</span>
        </div>
        
        <div class="nav-section-title">Vues Globales</div>
        <div style="padding: 0 12px 12px;">
            <div class="folder-item active" id="btn-all" onclick="filterByFolder('ALL')">
                <i class="fa-solid fa-globe"></i> Tous les liens
            </div>
            <div class="folder-item" id="btn-recent" onclick="filterByRecent()">
                <i class="fa-solid fa-clock"></i> Ajouts Recents
            </div>
        </div>

        <div class="nav-section-title">Directory Tree</div>
        <div class="folder-tree" id="folder-list"></div>
    </aside>

    <main class="main-content">
        <header class="topbar">
            <div class="search-wrapper">
                <i class="fa-solid fa-search"></i>
                <input type="text" class="search-input" id="search" placeholder="Recherche globale (titre, #tag, url)..." onkeyup="handleSearch()">
            </div>
            
            <div class="view-controls">
                <button class="btn-view active" onclick="switchView('dashboard', event)" title="Vue Dashboard"><i class="fa-solid fa-border-all"></i></button>
                <button class="btn-view" onclick="switchView('cards', event)" title="Vue Cartes"><i class="fa-solid fa-grip"></i></button>
                <button class="btn-view" onclick="switchView('table', event)" title="Vue Table"><i class="fa-solid fa-list-ul"></i></button>
            </div>
        </header>
        
        <div class="workspace">
            <div class="folder-header">
                <h2 id="current-title"><i class="fa-solid fa-folder-open"></i> Tous les liens</h2>
                <div class="folder-stats" id="current-stats"></div>
            </div>
            
            <div id="view-dashboard" class="dashboard-container"></div>
            <div id="view-cards" class="cards-grid" style="display: none;"></div>
            <div id="view-table" style="display: none;">
                <table class="table-view">
                    <thead><tr><th>Titre</th><th>URL</th><th>Dossier</th><th>Tags</th></tr></thead>
                    <tbody id="table-body"></tbody>
                </table>
            </div>
        </div>
    </main>

    <script>
    // Global error handler - shows visible error panel instead of blank screen
    window.onerror = function(msg, src, line, col, err) {{
        document.body.innerHTML = '<div style="font-family:monospace;padding:40px;color:#ff4444;background:#0a0a0a;min-height:100vh">'
            + '<h2 style="color:#ff6666">&#9888; Dashboard JS Error</h2>'
            + '<pre style="background:#111;padding:20px;border:1px solid #333;overflow:auto;margin-top:16px">'
            + msg + '\\nLine ' + line + ':' + col + '\\n' + (err && err.stack ? err.stack : '') + '</pre>'
            + '<p style="color:#888;margin-top:20px">Regenerez avec la derniere version du script.</p>'
            + '</div>';
        return true;
    }};

        const rawBookmarks = {js_data_json};
        // folderOrder = DFS traversal order exactly as Firefox sidebar shows folders
        const folderOrder = {folder_order_json};
        // Map folder path -> its DFS index for fast O(1) lookup
        const folderOrderMap = {{}};
        folderOrder.forEach((p, i) => {{ folderOrderMap[p] = i; }});

        function getFolderSortKey(path) {{
            // Known folder: use DFS index. Unknown: push to end.
            const idx = folderOrderMap[path];
            return idx !== undefined ? idx : 99999;
        }}
        
        let folderMap = {{}};
        rawBookmarks.forEach(b => {{
            const path = b.folder || 'Unsorted';
            if (!folderMap[path]) folderMap[path] = [];
            folderMap[path].push(b);
        }});
        // Order uniquePaths by DFS traversal index (Firefox sidebar order)
        const uniquePaths = Object.keys(folderMap).sort((a, b) => getFolderSortKey(a) - getFolderSortKey(b));

        const tree = {{}};
        uniquePaths.forEach(path => {{
            const parts = path.split(' > ');
            let currentLevel = tree;
            let currentPath = '';
            parts.forEach((part, index) => {{
                currentPath = index === 0 ? part : currentPath + ' > ' + part;
                if (!currentLevel[part]) {{
                    currentLevel[part] = {{ _fullPath: currentPath }};
                }}
                currentLevel = currentLevel[part];
            }});
        }});

        function buildTreeHTML(nodeObj, isRoot) {{
            isRoot = isRoot || false;
            let html = '<div class="folder-node' + (isRoot ? ' root-node' : '') + '">';
            const keys = Object.keys(nodeObj).filter(k => k !== '_fullPath'); // preserve Firefox order
            keys.forEach(function(key) {{
                const fullPath = nodeObj[key]._fullPath || key;
                const hasChildren = Object.keys(nodeObj[key]).filter(k => k !== '_fullPath').length > 0;
                const toggleHtml = hasChildren
                    ? '<i class="fa-solid fa-chevron-right folder-toggle" onclick="toggleFolder(event, this)"></i>'
                    : '<span style="width:16px;display:inline-block"></span>';
                const iconHtml = hasChildren
                    ? '<i class="fa-solid fa-folder"></i>'
                    : '<i class="fa-regular fa-folder"></i>';
                // Use data-path attribute instead of inline onclick string to avoid ALL quoting issues
                // (folder names may contain single quotes, double quotes, backslashes)
                const safeTitle = fullPath.replace(/"/g, '&quot;');
                html += '<div class="folder-item" data-path="' + safeTitle + '" title="' + safeTitle + '" onclick="selectFolder(this.dataset.path, this)">';
                html += toggleHtml + iconHtml + '<span>' + escHtml(key) + '</span></div>';
                if (hasChildren) {{
                    html += buildTreeHTML(nodeObj[key], false);
                }}
            }});
            html += '</div>';
            return html;
        }}

        document.getElementById('folder-list').innerHTML = buildTreeHTML(tree, true);

        function toggleFolder(e, toggleIcon) {{
            e.stopPropagation();
            const itemDiv = toggleIcon.closest('.folder-item');
            const childrenContainer = itemDiv.nextElementSibling;
            const folderIcon = itemDiv.querySelector('.fa-folder, .fa-folder-open');
            if (childrenContainer && childrenContainer.classList.contains('folder-node')) {{
                if (childrenContainer.classList.contains('expanded')) {{
                    childrenContainer.classList.remove('expanded');
                    toggleIcon.classList.replace('fa-chevron-down', 'fa-chevron-right');
                    if (folderIcon) folderIcon.className = 'fa-solid fa-folder';
                }} else {{
                    childrenContainer.classList.add('expanded');
                    toggleIcon.classList.replace('fa-chevron-right', 'fa-chevron-down');
                    if (folderIcon) folderIcon.className = 'fa-solid fa-folder-open';
                }}
            }}
        }}

        function selectFolder(fullPath, clickedElement) {{
            document.querySelectorAll('.folder-item').forEach(i => i.classList.remove('active'));
            if (clickedElement) clickedElement.classList.add('active');
            filterByFolder(fullPath, false);
        }}

        let currentMode = 'ALL';
        let currentQuery = '';
        let currentActiveView = 'dashboard';

        function switchView(viewName, evt) {{
            currentActiveView = viewName;
            document.querySelectorAll('.btn-view').forEach(b => b.classList.remove('active'));
            if (evt && evt.currentTarget) evt.currentTarget.classList.add('active');
            document.getElementById('view-dashboard').style.display = 'none';
            document.getElementById('view-cards').style.display = 'none';
            document.getElementById('view-table').style.display = 'none';
            if (viewName === 'dashboard') document.getElementById('view-dashboard').style.display = 'block';
            else if (viewName === 'cards') document.getElementById('view-cards').style.display = 'grid';
            else if (viewName === 'table') document.getElementById('view-table').style.display = 'block';
            renderData(currentMode, currentQuery);
        }}

        function filterByFolder(folder, updateVisuals) {{
            if (updateVisuals === undefined) updateVisuals = true;
            currentMode = folder;
            if (updateVisuals) {{
                document.querySelectorAll('.folder-item').forEach(i => i.classList.remove('active'));
                if (folder === 'ALL') document.getElementById('btn-all').classList.add('active');
            }}
            document.getElementById('search').value = '';
            currentQuery = '';
            renderData(currentMode, currentQuery);
        }}
        
        function filterByRecent() {{
            currentMode = 'RECENT';
            document.querySelectorAll('.folder-item').forEach(i => i.classList.remove('active'));
            document.getElementById('btn-recent').classList.add('active');
            document.getElementById('search').value = '';
            currentQuery = '';
            renderData(currentMode, currentQuery);
        }}

        function handleSearch() {{
            currentQuery = document.getElementById('search').value.toLowerCase();
            renderData(currentMode, currentQuery);
        }}
        
        function getInitials(title) {{
            if (!title) return '?';
            return title.charAt(0).toUpperCase();
        }}

        function escHtml(str) {{
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }}

        function getHostname(url) {{
            try {{ return new URL(url).hostname.replace('www.', ''); }} catch(e) {{ return url; }}
        }}

        function renderData(mode, query) {{
            let filtered = rawBookmarks.slice();
            let headerTitle = 'Tous les liens';
            let headerIcon = 'fa-globe';

            if (mode === 'RECENT') {{
                filtered = filtered.slice().reverse().slice(0, 50);
                headerTitle = '50 Derniers Ajouts';
                headerIcon = 'fa-clock';
            }} else if (mode !== 'ALL') {{
                filtered = filtered.filter(b => b.folder === mode || b.folder.startsWith(mode + ' > '));
                const parts = mode.split(' > ');
                headerTitle = parts[parts.length - 1];
                headerIcon = 'fa-folder-open';
            }}

            if (query) {{
                filtered = filtered.filter(b =>
                    (b.title && b.title.toLowerCase().includes(query)) ||
                    (b.url && b.url.toLowerCase().includes(query)) ||
                    (b.tags && b.tags.toLowerCase().includes(query))
                );
                headerTitle = 'Recherche: "' + query + '"';
                headerIcon = 'fa-magnifying-glass';
            }}

            document.getElementById('current-title').innerHTML = '<i class="fa-solid ' + headerIcon + '"></i> ' + escHtml(headerTitle);
            document.getElementById('current-stats').innerText = filtered.length + ' signet(s) affiche(s)';

            const vDash = document.getElementById('view-dashboard');
            const vCards = document.getElementById('view-cards');
            const vTable = document.getElementById('table-body');
            vDash.innerHTML = '';
            vCards.innerHTML = '';
            vTable.innerHTML = '';

            if (filtered.length === 0) {{
                const emptyHtml = '<div class="empty-state"><i class="fa-solid fa-ghost"></i><p>Aucun resultat trouve.</p></div>';
                if (currentActiveView === 'dashboard') vDash.innerHTML = emptyHtml;
                if (currentActiveView === 'cards') vCards.innerHTML = emptyHtml;
                if (currentActiveView === 'table') vTable.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;">Aucune donnee</td></tr>';
                return;
            }}

            if (currentActiveView === 'dashboard') {{
                const widgetMap = {{}};
                filtered.forEach(b => {{
                    const cat = b.folder || 'General';
                    if (!widgetMap[cat]) widgetMap[cat] = [];
                    widgetMap[cat].push(b);
                }});
                const dashParts = [];
                // Sort widgets by Firefox DFS traversal order
                Object.keys(widgetMap).sort((a, b) => getFolderSortKey(a) - getFolderSortKey(b)).forEach(fullPath => {{
                    const items = widgetMap[fullPath];
                    
                    let catTitle;
                    if (mode === 'ALL' || mode === 'RECENT' || query) {{
                        catTitle = escHtml((fullPath || 'Root').replace(/ > /g, ' / '));
                    }} else {{
                        const prefix = mode + ' > ';
                        if (fullPath === mode) {{
                            catTitle = '<span style="color:var(--text-muted);font-style:italic">(racine du dossier)</span>';
                        }} else if (fullPath.startsWith(prefix)) {{
                            catTitle = escHtml(fullPath.slice(prefix.length).replace(/ > /g, ' / '));
                        }} else {{
                            catTitle = escHtml(fullPath.replace(/ > /g, ' / '));
                        }}
                    }}
                    
                    const itemsHtml = items.map(b => {{
                        const hostname = escHtml(getHostname(b.url));
                        const tagLine = (mode === 'ALL' || query) && b.tags
                            ? '<div class="list-item-url" style="color:var(--accent-glow)">#' + escHtml(b.tags.split(',')[0]) + '</div>'
                            : '<div class="list-item-url">' + hostname + '</div>';
                        return '<a href="' + escHtml(b.url) + '" target="_blank" class="list-item" title="' + escHtml(b.url) + '">'
                            + '<div class="list-item-favicon">' + getInitials(b.title) + '</div>'
                            + '<div class="list-item-details">'
                            + '<div class="list-item-title">' + escHtml(b.title) + '</div>'
                            + tagLine
                            + '</div></a>';
                    }}).join('');
                    dashParts.push('<div class="widget-group">'
                        + '<div class="widget-header" title="' + escHtml(fullPath) + '">'
                        + '<i class="fa-solid fa-bookmark"></i> ' + catTitle
                        + ' <span style="margin-left:auto;font-size:0.7rem;color:var(--border-active)">' + items.length + '</span></div>'
                        + '<div class="widget-content">' + itemsHtml + '</div></div>');
                }});
                vDash.innerHTML = dashParts.join('');
            }} else if (currentActiveView === 'cards') {{
                const cardParts = [];
                filtered.forEach(b => {{
                    let tagsHtml = '';
                    if (b.tags) {{
                        const tagsArr = b.tags.split(',').filter(t => t.trim() !== '');
                        if (tagsArr.length > 0) {{
                            tagsHtml = '<div class="bmc-tags">' + tagsArr.map(t => '<span class="bmc-tag">' + escHtml(t) + '</span>').join('') + '</div>';
                        }}
                    }}
                    const folderDisplay = escHtml((b.folder || '').replace(/ > /g, ' / '));
                    cardParts.push('<a href="' + escHtml(b.url) + '" target="_blank" class="bmc-card" title="' + escHtml(b.url) + '">'
                        + '<div class="bmc-header">'
                        + '<div class="bmc-icon"><i class="fa-solid fa-link"></i></div>'
                        + '<div class="bmc-info">'
                        + '<div class="bmc-title">' + escHtml(b.title) + '</div>'
                        + '<div class="bmc-folder">' + folderDisplay + '</div>'
                        + '</div></div>'
                        + tagsHtml
                        + '<div class="bmc-url">' + escHtml(b.url) + '</div></a>');
                }});
                vCards.innerHTML = cardParts.join('');
            }} else if (currentActiveView === 'table') {{
                const rowParts = [];
                filtered.forEach(b => {{
                    let tags = b.tags ? b.tags.split(',').map(t => '<code>#' + escHtml(t.trim()) + '</code>').join(' ') : '-';
                    rowParts.push('<tr>'
                        + '<td><a href="' + escHtml(b.url) + '" target="_blank" class="tbl-title" title="' + escHtml(b.title) + '">' + escHtml(b.title) + '</a></td>'
                        + '<td><div class="tbl-url" title="' + escHtml(b.url) + '">' + escHtml(b.url) + '</div></td>'
                        + '<td>' + escHtml(b.folder || '') + '</td>'
                        + '<td>' + tags + '</td>'
                        + '</tr>');
                }});
                vTable.innerHTML = rowParts.join('');
            }}
        }}

        renderData('ALL', '');
    </script>
</body>
</html>"""

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"[*] Dashboard bmctl genere avec succes : {output_path}")


# ==============================================================================
# EXPORTATEUR
# ==============================================================================

class BookmarkExporter:
    
    @staticmethod
    def _microsecs_to_datetime(microsecs):
        if not microsecs:
            return ""
        try:
            secs = microsecs / 1_000_000
            return datetime.datetime.fromtimestamp(secs).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return ""

    @staticmethod
    def _prepare_data(db: BookmarkDatabase):
        data = []
        for node in db.nodes:
            data.append({
                "Titre": node.title,
                "URL": node.original_url,
                "Dossier": node.path,
                "Tags": node.tags,
                "Date_Ajout": BookmarkExporter._microsecs_to_datetime(node.date_added)
            })
        return data

    @staticmethod
    def to_csv(db: BookmarkDatabase, output_path: str):
        data = BookmarkExporter._prepare_data(db)
        if not data:
            print("[!] Aucune donnee a exporter.")
            return
        keys = data[0].keys()
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            dict_writer = csv.DictWriter(f, keys)
            dict_writer.writeheader()
            dict_writer.writerows(data)
        print(f"[*] Export CSV genere avec succes : {output_path}")

    @staticmethod
    def to_excel(db: BookmarkDatabase, output_path: str):
        try:
            df = pd.DataFrame(BookmarkExporter._prepare_data(db))
            df.to_excel(output_path, index=False, engine='openpyxl')
            print(f"[*] Export Excel (.xlsx) genere avec succes : {output_path}")
        except ImportError:
            print("[!] Erreur : installez pandas et openpyxl.")
            print("    Lancez : pip install pandas openpyxl")
            
    @staticmethod
    def to_markdown(db: BookmarkDatabase, output_path: str):
        try:
            folders = defaultdict(list)
            for node in db.nodes:
                folders[node.path].append(node)
                
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("# Bookmarks\n\n")
                for path in sorted(folders.keys()):
                    f.write(f"## {path}\n")
                    for node in folders[path]:
                        tags_str = f" `[{node.tags}]`" if node.tags else ""
                        title_clean = node.title.replace('\n', ' ').strip()
                        date_str = BookmarkExporter._microsecs_to_datetime(node.date_added)
                        date_display = f" *(ajout le {date_str})*" if date_str else ""
                        f.write(f"- [{title_clean}]({node.original_url}){tags_str}{date_display}\n")
                    f.write("\n")
            print(f"[*] Export Markdown (.md) genere avec succes : {output_path}")
        except Exception as e:
            print(f"[!] Erreur lors de l'export Markdown : {e}")


# ==============================================================================
# CLI
# ==============================================================================

import re

def _fix_wsl_path(path: str) -> str:
    """
    Detect Windows paths with stripped backslashes (WSL bash without quoting).

    Root cause: passing  -o C:\\Users\\foo\\bar.html  in bash WITHOUT quotes
    strips the backslashes because \\U \\f \\D are not valid bash escapes.
    Result: the tool receives  C:UsersfooDesktopbar.html  - unrecoverable.

    This function detects the pattern and aborts with clear instructions.
    """
    # Valid paths - pass through unchanged
    if path.startswith('/') or re.match(r'^[A-Za-z]:[/\\]', path):
        return path

    # Detect stripped path: drive letter + colon + alpha (no separator)
    stripped_match = re.match(r'^([A-Za-z]):([A-Za-z].*)$', path)
    if stripped_match:
        drive = stripped_match.group(1).lower()
        print()
        print("=" * 65)
        print("  ERREUR FATALE - CHEMIN WINDOWS MAL FORME (WSL)")
        print("=" * 65)
        print(f"  Chemin recu  : '{path}'")
        print(f"  Probleme     : les '\\' ont ete stripes par bash (sans guillemets)")
        print()
        print("  Solutions (choisissez UNE) :")
        print(f"    1) Chemin WSL Linux (recommande) :")
        print(f"       -o /mnt/{drive}/Users/fferman/Desktop/dashboard.html")
        print(f"    2) Chemin Windows entre guillemets :")
        print(f"       -o 'C:\\Users\\fferman\\Desktop\\dashboard.html'")
        print(f"    3) Chemin Windows avec slashes avant :")
        print(f"       -o C:/Users/fferman/Desktop/dashboard.html")
        print("=" * 65)
        print()
        raise SystemExit(1)

    return path


def main():
    parser = argparse.ArgumentParser(description="Toolkit avance pour la gestion de favoris.")
    subparsers = parser.add_subparsers(dest='command', required=True)

    parser_audit = subparsers.add_parser('audit', help="Auditer un seul fichier de favoris")
    parser_audit.add_argument('-i', '--input', required=True)
    parser_audit.add_argument('--top', type=int, default=10)
    parser_audit.add_argument('--show-short', action='store_true')
    parser_audit.add_argument('--show-tree', action='store_true',
        help="Afficher l'arbre de dossiers tel que lu depuis le JSON (debug ordre/hierarchie)")

    parser_compare = subparsers.add_parser('compare', help="Comparer deux fichiers")
    parser_compare.add_argument('-o', '--old', required=True)
    parser_compare.add_argument('-n', '--new', required=True)
    group = parser_compare.add_mutually_exclusive_group()
    group.add_argument('--show-full', action='store_true')
    group.add_argument('--show-short', action='store_true')
    
    parser_export = subparsers.add_parser('export', help="Exporter vers CSV/xlsx/md")
    parser_export.add_argument('-i', '--input', required=True)
    parser_export.add_argument('--format', choices=['csv', 'xlsx', 'md'], required=True)
    parser_export.add_argument('-o', '--output', required=True)

    parser_merge = subparsers.add_parser('merge', help="Fusionner deux fichiers")
    parser_merge.add_argument('-b', '--base', required=True)
    parser_merge.add_argument('-n', '--new', required=True)
    parser_merge.add_argument('-o', '--output', required=True)
    parser_merge.add_argument('--no-confirm', action='store_true')

    parser_dashboard = subparsers.add_parser('dashboard', help="Generer un dashboard HTML interactif")
    parser_dashboard.add_argument('-i', '--input', required=True)
    parser_dashboard.add_argument('-o', '--output', default="dashboard.html")

    args = parser.parse_args()

    # Fix Windows paths with stripped backslashes (WSL bash without quotes)
    if hasattr(args, 'output') and args.output:
        args.output = _fix_wsl_path(args.output)

    if args.command == 'audit':
        if not os.path.isfile(args.input):
            print(f"[!] Erreur : '{args.input}' introuvable.")
            return
        db = BookmarkDatabase()
        db.load_firefox_json(args.input)
        BookmarkAuditor(db).print_report(show_top=args.top, show_short=args.show_short, show_tree=args.show_tree)

    elif args.command == 'compare':
        if not os.path.isfile(args.old) or not os.path.isfile(args.new):
            print("[!] Erreur : Les deux fichiers JSON doivent exister.")
            return
        print("[*] Chargement de l'ancien export...")
        db_old = BookmarkDatabase()
        db_old.load_firefox_json(args.old)
        print("[*] Chargement du nouvel export...")
        db_new = BookmarkDatabase()
        db_new.load_firefox_json(args.new)
        BookmarkComparator.compare(db_old, db_new, show_full=args.show_full, show_short=args.show_short)

    elif args.command == 'export':
        if not os.path.isfile(args.input):
            print(f"[!] Erreur : '{args.input}' introuvable.")
            return
        db = BookmarkDatabase()
        db.load_firefox_json(args.input)
        if args.format == 'csv':
            BookmarkExporter.to_csv(db, args.output)
        elif args.format == 'xlsx':
            BookmarkExporter.to_excel(db, args.output)
        elif args.format == 'md':
            BookmarkExporter.to_markdown(db, args.output)

    elif args.command == 'merge':
        if not os.path.isfile(args.base) or not os.path.isfile(args.new):
            print("[!] Erreur : Les deux fichiers JSON doivent exister.")
            return
        print("[*] Chargement de la base principale...")
        db_base = BookmarkDatabase()
        db_base.load_firefox_json(args.base)
        print("[*] Chargement du fichier a integrer...")
        db_new = BookmarkDatabase()
        db_new.load_firefox_json(args.new)
        BookmarkMerger.merge(db_base, db_new, args.no_confirm, args.output)

    elif args.command == 'dashboard':
        if not os.path.isfile(args.input):
            print(f"[!] Erreur : '{args.input}' introuvable.")
            return
        print(f"[*] Chargement des favoris pour le Dashboard...")
        db = BookmarkDatabase()
        db.load_firefox_json(args.input)
        BookmarkDashboardGen.generate(db, args.output)


if __name__ == "__main__":
    main()
