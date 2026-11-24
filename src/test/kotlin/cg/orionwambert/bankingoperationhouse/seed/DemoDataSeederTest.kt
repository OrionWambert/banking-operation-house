package cg.orionwambert.bankingoperationhouse.seed

import cg.orionwambert.bankingoperationhouse.TestcontainersConfiguration
import cg.orionwambert.bankingoperationhouse.operation.BankingOperation
import cg.orionwambert.bankingoperationhouse.operation.BankingOperationRepository
import cg.orionwambert.bankingoperationhouse.operation.OperationType
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.context.annotation.Import
import java.time.Clock
import java.time.LocalDateTime
import java.time.ZoneOffset
import kotlin.random.Random
import kotlin.test.assertEquals
import kotlin.test.assertTrue

@SpringBootTest(properties = ["app.seed.enabled=false"])
@Import(TestcontainersConfiguration::class)
class DemoDataSeederTest {

    @Autowired lateinit var repository: BankingOperationRepository

    private val now = LocalDateTime.of(2026, 11, 24, 12, 0)
    private val clock = Clock.fixed(now.toInstant(ZoneOffset.UTC), ZoneOffset.UTC)

    private fun seeder(count: Int, chunkSize: Int = 100, clients: Int = 10) =
        DemoDataSeeder(repository, SeedProperties(enabled = true, count = count, chunkSize = chunkSize, clients = clients), clock, Random(42))

    @AfterEach
    fun cleanUp() = repository.deleteAll()

    @Test
    fun `fills an empty table up to the target, across several chunks`() {
        assertEquals(250, seeder(count = 250).seed())
        assertEquals(250, repository.count())
    }

    @Test
    fun `tops up a partially filled table instead of skipping it`() {
        repository.saveAll(List(40) { BankingOperation(clientName = "Existing $it", amount = 1) })

        assertEquals(60, seeder(count = 100).seed())
        assertEquals(100, repository.count())
    }

    @Test
    fun `does nothing once the target is reached`() {
        seeder(count = 50).seed()

        assertEquals(0, seeder(count = 50).seed())
        assertEquals(0, seeder(count = 10).seed())
        assertEquals(50, repository.count())
    }

    @Test
    fun `generates plausible operations`() {
        seeder(count = 500, clients = 10).seed()
        val operations = repository.findAll()

        assertTrue(operations.all { it.amount in 1 until 1_000_000 })
        assertTrue(operations.all { !it.operationDate.isAfter(now) && it.operationDate.isAfter(now.minusYears(1).minusDays(1)) })
        assertTrue(operations.map { it.clientName }.toSet().size <= 10)
        assertEquals(OperationType.entries.toSet(), operations.map { it.operationType }.toSet())
    }

    @Test
    fun `rejects invalid settings`() {
        assertThrows<IllegalArgumentException> { SeedProperties(count = -1) }
        assertThrows<IllegalArgumentException> { SeedProperties(chunkSize = 0) }
        assertThrows<IllegalArgumentException> { SeedProperties(clients = 0) }
    }
}
