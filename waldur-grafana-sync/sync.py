import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from functools import cached_property

from backend import BACKEND_API_USER, Backend
from waldur_client import WaldurClient

handler = logging.StreamHandler(sys.stdout)
logger = logging.getLogger(__name__)
formatter = logging.Formatter('[%(levelname)s] [%(asctime)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

WALDUR_API_URL = os.environ['WALDUR_API_URL']
WALDUR_API_TOKEN = os.environ['WALDUR_API_TOKEN']

REGISTRATION_METHOD = os.environ.get('REGISTRATION_METHOD', 'eduteams')
STAFF_TEAM_NAME = os.environ.get('STAFF_TEAM_NAME', 'staff')
SUPPORT_TEAM_NAME = os.environ.get('SUPPORT_TEAM_NAME', 'support')
DATASOURCE_UID = os.environ['DATASOURCE_UID']

PROTECTED_USERNAMES = os.environ.get(
    'PROTECTED_USERNAMES', 'admin,' + BACKEND_API_USER
).split(',')
PROTECTED_TEAMS = os.environ.get('PROTECTED_TEAMS', 'Development,Management').split(',')

ALL_SPECIAL_TEAMS = [STAFF_TEAM_NAME, SUPPORT_TEAM_NAME] + PROTECTED_TEAMS
DRY_RUN = os.environ.get('DRY_RUN', 'True') in ('TRUE', 'True', 'true', 'yes')


@dataclass
class User:
    uuid: str
    username: str
    email: str
    name: str
    is_staff: bool = False
    is_support: bool = False


@dataclass
class Organisation:
    uuid: str
    name: str
    division: str
    abbreviation: str = ''
    country: str = ''
    is_service_provider: bool = False
    owners: list[User] = field(default_factory=list)


def is_uuid_like(val):
    '''
    Check if value looks like a valid UUID.
    '''
    try:
        uuid.UUID(val)
    except (TypeError, ValueError, AttributeError):
        return False
    else:
        return True


class Sync:
    @cached_property
    def grafana_client(self):
        return Backend()

    @cached_property
    def waldur_client(self):
        return WaldurClient(WALDUR_API_URL, WALDUR_API_TOKEN)

    def run(self):
        self.sync_users()
        self.sync_organization_teams()
        self.sync_staff_team()
        self.sync_support_team()
        self.sync_folders()
        self.sync_dashboards()

    @property
    def waldur_staff_users(self):
        return [user for user in self.waldur_users if user.is_staff]

    @property
    def waldur_support_users(self):
        return [user for user in self.waldur_users if user.is_support]

    @cached_property
    def waldur_organizations(self):
        query = {
            'archived': False,
            'is_active': True,
            'field': [
                'name',
                'abbreviation',
                'country',
                'division_name',
                'uuid',
                'owners',
                'is_service_provider',
            ],
        }

        return {
            c['uuid']: Organisation(
                c['uuid'],
                c['name'],
                c.get('division_name', ''),
                c['abbreviation'],
                c['country'],
                c['is_service_provider'],
                [
                    User(u['uuid'], u['username'], u['email'], u['full_name'])
                    for u in c['owners']
                ],
            )
            for c in self.waldur_client.list_customers(query)
        }

    @cached_property
    def waldur_users(self):
        result = []
        query = {
            'registration_method': REGISTRATION_METHOD,
            'is_active': True,
            'field': [
                'customer_permissions',
                'is_staff',
                'is_support',
                'username',
                'uuid',
                'full_name',
                'email',
            ],
        }

        for item in self.waldur_client.list_users(query):
            organizations = [
                Organisation(
                    p['customer_uuid'],
                    p['customer_name'],
                    p.get('customer_division_name', ''),
                )
                for p in item['customer_permissions']
                if p['role'] == 'owner'
            ]
            if not item['is_staff'] and not item['is_support'] and not organizations:
                continue

            result.append(
                User(
                    uuid=item['uuid'],
                    username=item['username'],
                    email=item['email'],
                    name=item['full_name'],
                    is_staff=item['is_staff'],
                    is_support=item['is_support'],
                )
            )
        return result

    def sync_folders(self):
        # assure that for each organization in waldur we have a folder
        grafana_folders = {
            f['uid']: f['title'] for f in self.grafana_client.list_folders()
        }
        folder_names = set(grafana_folders.values())
        for org_uuid, waldur_org in self.waldur_organizations.items():
            abbreviation = (
                f' ({waldur_org.abbreviation})' if waldur_org.abbreviation else ''
            )
            expected_title = f'{waldur_org.name}{abbreviation}'
            if org_uuid in grafana_folders:
                # check if name needs updates
                if grafana_folders[org_uuid] != expected_title:
                    logger.info(
                        f'Updating folder with UID {org_uuid}. {grafana_folders[org_uuid]} -> {expected_title}'
                    )
                    self.grafana_client.update_folder(org_uuid, expected_title)
            else:
                if expected_title in folder_names:
                    print(f'Duplicate {expected_title} is detected')
                    continue
                # create a new one
                logger.info(f'Adding folder {expected_title} with UID {org_uuid}.')
                if not DRY_RUN:
                    self.grafana_client.create_folder(expected_title, org_uuid)
                folder_names.add(expected_title)
            # make sure that corresponding tean has read access to a folder
            if not DRY_RUN:
                self.grafana_client.set_folder_permissions(org_uuid, expected_title)

        # cleanup existing folders with UUID like unique keys
        for folder_uid in grafana_folders.keys():
            if is_uuid_like(folder_uid) and folder_uid not in self.waldur_organizations:
                logger.info(
                    f'Removing folder {grafana_folders[folder_uid]} with UID {folder_uid}.'
                )
                if not DRY_RUN:
                    self.grafana_client.delete_folder(folder_uid)

    def member_of(self, user_id, teams_list):
        user_teams = {t['name'] for t in self.grafana_client.list_user_teams(user_id)}
        return len(user_teams.intersection(teams_list)) > 0

    def sync_users(self):
        grafana_users = self.grafana_client.list_users()
        waldur_usernames = [waldur_user.username for waldur_user in self.waldur_users]
        for grafana_user in grafana_users:
            if (
                grafana_user['login'] not in waldur_usernames
                and grafana_user['login'] not in PROTECTED_USERNAMES
                and not self.member_of(grafana_user['id'], ALL_SPECIAL_TEAMS)
            ):
                logger.info(
                    f'User {grafana_user["login"]} / {grafana_user["email"]} does not have any managed roles.'
                )

        for waldur_user in self.waldur_users:
            if waldur_user.username not in [
                grafana_user['login'] for grafana_user in grafana_users
            ]:
                if not DRY_RUN:
                    self.grafana_client.create_user(
                        email=waldur_user.email,
                        name=waldur_user.name,
                        login=waldur_user.username,
                    )
                logger.info(
                    f'User {waldur_user.username} / {waldur_user.email} has been created.'
                )

    def _sync_teams(self, team_name, waldur_users: list[User]):
        if not self.grafana_client.list_teams(team_name):
            if not DRY_RUN:
                team_id = self.grafana_client.create_team(team_name)['teamId']
            else:
                logger.info(
                    f'Team {team_name} creation not possible in dry run mode, skipping.'
                )
                return
            logger.info(f'Team {team_name} has been created.')
        else:
            team_id = self.grafana_client.list_teams(team_name)[0]['id']

        grafana_users = self.grafana_client.get_team_members(team_id)

        waldur_map = {user.username: user for user in waldur_users}
        grafana_map = {user['login']: user for user in grafana_users}

        new_usernames = set(waldur_map) - set(grafana_map)
        stale_usernames = set(grafana_map) - set(waldur_map)

        new_users = {waldur_map[username] for username in new_usernames}
        stale_users = {grafana_map[username] for username in stale_usernames}

        for user in stale_users:
            if not DRY_RUN:
                self.grafana_client.remove_team_member(team_id, user['userId'])
            logger.info(
                f'User {user["login"]} / {user["email"]} has been deleted from members of {team_name} / {team_id}.'
            )

        for user in new_users:
            if not DRY_RUN:
                self.grafana_client.create_team_member(
                    team_id, user.name, user.username, user.email
                )
            logger.info(
                f'User {user.username} / {user.email} has been added to members of {team_name} / {team_id}.'
            )

    def sync_staff_team(self):
        self._sync_teams(
            team_name=STAFF_TEAM_NAME,
            waldur_users=self.waldur_staff_users,
        )

    def sync_support_team(self):
        self._sync_teams(
            team_name=SUPPORT_TEAM_NAME,
            waldur_users=self.waldur_support_users,
        )

    def sync_organization_teams(self):
        grafana_teams = {f['name']: f['id'] for f in self.grafana_client.list_teams()}
        seen_org_names = []
        for waldur_org in self.waldur_organizations.values():
            abbreviation = (
                f' ({waldur_org.abbreviation})' if waldur_org.abbreviation else ''
            )
            expected_title = f'{waldur_org.name}{abbreviation}'
            seen_org_names.append(expected_title)
            if expected_title not in grafana_teams:
                if not DRY_RUN:
                    self.grafana_client.create_team(expected_title)
                logger.info(f'Team {expected_title} has been created.')

            self._sync_teams(expected_title, waldur_org.owners)

        # cleanup existing folders with UUID like unique keys
        for team_name in grafana_teams:
            if team_name not in seen_org_names and team_name not in ALL_SPECIAL_TEAMS:
                if not DRY_RUN:
                    pass
                    # self.grafana_client.delete_teams(team_name)
                logger.info(f'TEMPORARILY DISABLED. Team {team_name} has been deleted.')

    def sync_dashboards(self):
        self.waldur_organizations.keys()
        grafana_dashboards_list = self.grafana_client.search_dashboards(tag='managed')
        grafana_dashboards_map = {
            dashboard['folderUid']: dashboard
            for dashboard in grafana_dashboards_list
            if 'folderUid' in dashboard
        }
        folders = self.grafana_client.list_folders()
        folder_uids = {folder['uid'] for folder in folders}
        for waldur_org in self.waldur_organizations.values():
            if waldur_org.uuid not in folder_uids:
                continue
            grafana_dashboard = grafana_dashboards_map.get(waldur_org.uuid)
            dashboard = json.loads(
                self.dashboard_template.replace(
                    '$CUSTOMER_NAME$', waldur_org.name
                ).replace('$DATASOURCE_UID$', DATASOURCE_UID)
            )
            payload = {
                'dashboard': dashboard,
                'folderUid': waldur_org.uuid,
            }
            if not grafana_dashboard:
                if not DRY_RUN:
                    dashboard = self.grafana_client.create_or_update_dashboard(payload)
                logger.info(f'Dashboard {waldur_org.name} has been created.')
            elif grafana_dashboard:
                payload['dashboard']['uid'] = grafana_dashboard['uid']
                payload['dashboard']['version'] = (
                    grafana_dashboard.get('version', 0) + 1
                )
                payload['overwrite'] = True
                if not DRY_RUN:
                    dashboard = self.grafana_client.create_or_update_dashboard(payload)
                logger.info(f'Dashboard {waldur_org.name} has been updated.')

    @cached_property
    def dashboard_template(self):
        path = os.path.join(os.path.dirname(__file__), 'dashboard-usage.json')
        return open(path).read()
