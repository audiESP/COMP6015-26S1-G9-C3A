"""Opt-in PostgreSQL/API checks for grouped training resources.

RUN_POSTGRES_INTEGRATION_TESTS=1 enables these tests. A private schema and all
test data are rolled back; existing application tables are never modified.
"""

import os
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv
from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

import main
from app.repositories.training_repository import TrainingRepository
from app.schemas import TrainingMaterial


class TrainingSchemaTests(unittest.TestCase):
    def test_legacy_material_has_no_additional_resource_links(self):
        material = TrainingMaterial(
            id='legacy', topicId='topic', title='Existing PDF', type='pdf',
            sourceUrl='https://www.health.gov.au/example.pdf',
        )
        self.assertEqual(material.model_dump()['resourceLinks'], [])


@unittest.skipUnless(
    os.getenv('RUN_POSTGRES_INTEGRATION_TESTS') == '1' and os.getenv('DATABASE_URL'),
    'Set RUN_POSTGRES_INTEGRATION_TESTS=1 with DATABASE_URL to run PostgreSQL checks',
)
class TrainingResourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(
            os.environ['DATABASE_URL'], row_factory=dict_row, connect_timeout=10,
        )
        cls.addClassCleanup(cls.connection.close)
        cls.addClassCleanup(cls.connection.rollback)
        schema = sql.Identifier('training_test_' + uuid4().hex)
        cls.connection.execute(sql.SQL('CREATE SCHEMA {}').format(schema))
        cls.connection.execute(sql.SQL('SET LOCAL search_path TO {}').format(schema))
        cls.connection.execute("SET LOCAL statement_timeout = '20s'")
        migrations = Path(__file__).resolve().parents[1] / 'migrations'
        for path in sorted(migrations.glob('*.sql')):
            if 5 <= int(path.name[:3]) <= 8:
                cls.connection.execute(path.read_text(encoding='utf-8'))
        cls.before = cls.connection.execute(
            'SELECT * FROM c3a_app_training_materials ORDER BY id'
        ).fetchall()
        cls.connection.execute(
            (migrations / '009_training_material_resource_links.sql').read_text(encoding='utf-8')
        )
        cls.migration = (migrations / '010_training_resources_in_existing_materials.sql').read_text(encoding='utf-8')
        cls.connection.execute(cls.migration)

        class TransactionalRepository(TrainingRepository):
            @contextmanager
            def _connect(self):
                yield cls.connection

        cls.repository = TransactionalRepository()
        cls.client = TestClient(main.app)
        cls.addClassCleanup(cls.client.close)
        cls.repository_patch = patch.object(main, 'training_repository', cls.repository)
        cls.repository_patch.start()
        cls.addClassCleanup(cls.repository_patch.stop)

    def test_catalogue_preserves_every_original_file_excerpt_and_id(self):
        after = {
            row['id']: row for row in self.connection.execute(
                'SELECT * FROM c3a_app_training_materials'
            ).fetchall()
        }
        self.assertEqual(len(after), len(self.before) + 5)
        supplemented = {
            'CPR Training': 1,
            'Recognising and Responding to a Fall': 1,
            'Safe Transfer and Manual Handling': 1,
            'Hand Hygiene - The 5 Moments': 2,
        }
        for original in self.before:
            with self.subTest(title=original['title']):
                current = after[original['id']]
                changed_fields = {'summary', 'updated_at'} if original['title'] in supplemented else set()
                for key in original.keys() - changed_fields:
                    self.assertEqual(current[key], original[key], key)
                self.assertEqual(len(current['resource_links']), supplemented.get(original['title'], 0))
                if original['title'] in supplemented:
                    self.assertNotEqual(current['summary'], original['summary'])
                    self.assertNotIn('\n', current['summary'])
                    self.assertNotIn(current['source_url'], [link['url'] for link in current['resource_links']])

    def test_original_topics_keep_their_material_counts(self):
        topics = {topic['slug']: topic for topic in self.repository.list_topics()}
        for slug, count in {
            'emergency-response': 5, 'medication-support': 3,
            'manual-handling': 2, 'infection-control-hygiene': 1,
        }.items():
            self.assertEqual(topics[slug]['materialCount'], count)

    def test_cpr_api_keeps_original_source_and_separate_nsw_resource(self):
        response = self.client.get('/training/materials/search', params={'q': 'NSW Ambulance'})
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        cpr = results[0]
        original = next(row for row in self.before if row['title'] == 'CPR Training')
        self.assertEqual(cpr['id'], str(original['id']))
        self.assertEqual(cpr['sourceUrl'], original['source_url'])
        self.assertEqual(cpr['body'], original['body'])
        self.assertEqual(cpr['resourceLinks'][0]['title'], 'NSW Ambulance CPR Chart')

    def test_all_language_files_share_one_page_and_survive_api_serialization(self):
        topics_response = self.client.get('/training/topics')
        self.assertEqual(topics_response.status_code, 200)
        topic = next(t for t in topics_response.json()['topics'] if t['slug'] == 'skin-pressure-injury')
        self.assertEqual(topic['materialCount'], 1)
        response = self.client.get(f"/training/topics/{topic['id']}/materials")
        self.assertEqual(response.status_code, 200)
        materials = response.json()['materials']
        self.assertEqual(len(materials), 1)
        links = materials[0]['resourceLinks']
        self.assertEqual([link['language'] for link in links], [
            'en', 'ar', 'el', 'hi', 'it', 'ko', 'zh-Hant', 'zh-Hans', 'vi',
        ])
        self.assertEqual(len({link['url'] for link in links}), 9)
        expected_file_names = [
            'Pressure-Injury-Prevention-Information-for-Patients-and-Families-English.pdf',
            'arabic-pipp.pdf', 'greek-pipp.pdf', 'hindi-pipp.pdf', 'italian-pipp.pdf',
            'korean-pipp.pdf', 'chinesetrad-pipp.pdf', 'chinesesimp-pipp.pdf', 'vietnamese-pipp.pdf',
        ]
        for link, file_name in zip(links, expected_file_names):
            self.assertTrue(link['url'].endswith('/' + file_name))
            self.assertEqual(link['type'], 'pdf')
        self.assertIn('العربية', links[1]['title'])
        self.assertIn('繁體中文', links[6]['title'])
        self.assertIn('简体中文', links[7]['title'])

    def test_searching_native_titles_returns_the_grouped_material(self):
        for query in ['简体中文', '繁體中文', 'العربية', '한국어', 'Tiếng Việt']:
            with self.subTest(query=query):
                response = self.client.get('/training/materials/search', params={'q': query})
                self.assertEqual(response.status_code, 200)
                results = response.json()['results']
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]['topicSlug'], 'skin-pressure-injury')
                self.assertEqual(len(results[0]['resourceLinks']), 9)

    def test_pdf_and_official_page_are_available_together(self):
        result = self.repository.search_materials('The Aged Care Infection Prevention and Control Guide')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['title'], 'Hand Hygiene - The 5 Moments')
        links = result[0]['resourceLinks']
        self.assertEqual([link['type'] for link in links], ['pdf', 'link'])
        self.assertIn('The-Aged-Care-Infection-Prevention-and-Control-Guide.pdf', links[0]['url'])
        self.assertEqual(links[1]['url'], 'https://www.safetyandquality.gov.au/resources/aged-care-infection-prevention-and-control-guide')
        self.assertIn('know-the-5-moments', result[0]['sourceUrl'])

    def test_migration_can_be_reapplied_without_duplicates_or_changes(self):
        before = self.connection.execute(
            'SELECT * FROM c3a_app_training_materials ORDER BY id'
        ).fetchall()
        self.connection.execute(self.migration)
        after = self.connection.execute(
            'SELECT * FROM c3a_app_training_materials ORDER BY id'
        ).fetchall()
        self.assertEqual(after, before)
        self.assertEqual(sum(len(row['resource_links']) for row in after), 19)


if __name__ == '__main__':
    unittest.main()
