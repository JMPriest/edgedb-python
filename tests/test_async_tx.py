#
# This source file is part of the EdgeDB open source project.
#
# Copyright 2016-present MagicStack Inc. and the EdgeDB authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import asyncio
import itertools

import edgedb

from edgedb import _testbase as tb
from edgedb import TransactionOptions
from edgedb.options import RetryOptions


class TestAsyncTx(tb.AsyncQueryTestCase):

    SETUP = '''
        CREATE TYPE test::TransactionTest EXTENDING std::Object {
            CREATE PROPERTY name -> std::str;
        };
    '''

    TEARDOWN = '''
        DROP TYPE test::TransactionTest;
    '''

    async def test_async_transaction_regular_01(self):
        tr = self.client.with_retry_options(
            RetryOptions(attempts=1)).transaction()

        with self.assertRaises(ZeroDivisionError):
            async for with_tr in tr:
                async with with_tr:
                    await with_tr.execute('''
                        INSERT test::TransactionTest {
                            name := 'Test Transaction'
                        };
                    ''')

                    1 / 0

        result = await self.client.query('''
            SELECT
                test::TransactionTest
            FILTER
                test::TransactionTest.name = 'Test Transaction';
        ''')

        self.assertEqual(result, [])

    async def test_async_transaction_kinds(self):
        isolations = [
            None,
            edgedb.IsolationLevel.Serializable,
        ]
        booleans = [None, True, False]
        all = itertools.product(isolations, booleans, booleans)
        for isolation, readonly, deferrable in all:
            opt = dict(
                isolation=isolation,
                readonly=readonly,
                deferrable=deferrable,
            )
            # skip None
            opt = {k: v for k, v in opt.items() if v is not None}
            client = self.client.with_transaction_options(
                TransactionOptions(**opt)
            )
            async for tx in client.transaction():
                async with tx:
                    pass

    async def test_async_transaction_commit_failure(self):
        with self.assertRaises(edgedb.errors.QueryError):
            async for tx in self.client.transaction():
                async with tx:
                    await tx.execute("start migration to {};")
        self.assertEqual(await self.client.query_single("select 42"), 42)

    async def test_async_transaction_exclusive(self):
        async for tx in self.client.transaction():
            async with tx:
                query = "select sys::_sleep(0.01)"
                f1 = self.loop.create_task(tx.execute(query))
                f2 = self.loop.create_task(tx.execute(query))
                with self.assertRaisesRegex(
                    edgedb.InterfaceError,
                    "concurrent queries within the same transaction "
                    "are not allowed"
                ):
                    await asyncio.wait_for(f1, timeout=5)
                    await asyncio.wait_for(f2, timeout=5)
