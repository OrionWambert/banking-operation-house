package cg.orionwambert.bankingoperationhouse.operation

import cg.orionwambert.bankingoperationhouse.TestcontainersConfiguration
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.context.SpringBootTest
import org.springframework.context.annotation.Import
import org.springframework.jdbc.core.simple.JdbcClient
import java.time.LocalDateTime
import kotlin.test.assertEquals

/**
 * Runs against the Flyway schema with `ddl-auto=validate`, so the context only starts
 * if the migration and the entity agree.
 */
@SpringBootTest(properties = ["app.seed.enabled=false"])
@Import(TestcontainersConfiguration::class)
class BankingOperationRepositoryTest {

    @Autowired lateinit var repository: BankingOperationRepository
    @Autowired lateinit var jdbc: JdbcClient

    @AfterEach
    fun cleanUp() = repository.deleteAll()

    @Test
    fun `stores the columns the CDC pipeline replicates`() {
        val date = LocalDateTime.of(2026, 3, 14, 9, 30)
        val saved = repository.save(
            BankingOperation(clientName = "Client 7", amount = 12_500, operationDate = date, operationType = OperationType.DEBIT),
        )

        val row = jdbc.sql("select client_name, amount, operation_date, operation_type from banking_operation where id = ?")
            .param(saved.id)
            .query { rs, _ -> listOf(rs.getString(1), rs.getLong(2), rs.getTimestamp(3).toLocalDateTime(), rs.getString(4)) }
            .single()

        // operation_type is stored by name: ClickHouse queries and the Metabase filters rely on 'DEBIT' / 'CREDIT'
        assertEquals(listOf<Any>("Client 7", 12_500L, date, "DEBIT"), row)
    }

    @Test
    fun `ids come from the sequence so inserts can be batched`() {
        val ids = repository.saveAll(List(3) { BankingOperation(clientName = "Client $it", amount = 1) }).map { it.id!! }

        assertEquals(ids.sorted(), ids)
        assertEquals(3, ids.toSet().size)
    }
}
