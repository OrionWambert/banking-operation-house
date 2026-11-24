package cg.orionwambert.bankingoperationhouse.seed

import cg.orionwambert.bankingoperationhouse.operation.BankingOperation
import cg.orionwambert.bankingoperationhouse.operation.BankingOperationRepository
import cg.orionwambert.bankingoperationhouse.operation.OperationType
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.ApplicationArguments
import org.springframework.boot.ApplicationRunner
import org.springframework.boot.autoconfigure.condition.ConditionalOnBooleanProperty
import org.springframework.stereotype.Component
import java.time.Clock
import java.time.LocalDateTime
import kotlin.random.Random

/**
 * Fills `banking_operation` with synthetic operations up to [SeedProperties.count].
 *
 * It tops up rather than skips, so restarting with a higher target adds only the missing rows,
 * which is what gives the CDC pipeline a steady stream of inserts to replicate.
 */
@Component
@ConditionalOnBooleanProperty("app.seed.enabled")
class DemoDataSeeder(
    private val repository: BankingOperationRepository,
    private val properties: SeedProperties,
    private val clock: Clock,
    private val random: Random,
) : ApplicationRunner {

    @Autowired
    constructor(repository: BankingOperationRepository, properties: SeedProperties) :
        this(repository, properties, Clock.systemDefaultZone(), Random.Default)

    private val log = LoggerFactory.getLogger(javaClass)

    override fun run(args: ApplicationArguments) {
        seed()
    }

    /** Inserts the missing operations and returns how many were added. */
    fun seed(): Int {
        val existing = repository.count()
        val missing = (properties.count - existing).coerceAtLeast(0).toInt()
        if (missing == 0) {
            log.info("banking_operation already has {} rows (target {}), nothing to seed", existing, properties.count)
            return 0
        }
        log.info("banking_operation has {} rows, seeding {} more up to {}", existing, missing, properties.count)

        val now = LocalDateTime.now(clock)
        var inserted = 0
        // One transaction per chunk (saveAll is transactional), so memory stays flat whatever the target
        while (inserted < missing) {
            val size = minOf(properties.chunkSize, missing - inserted)
            repository.saveAll(List(size) { randomOperation(now) })
            inserted += size
            log.info("Seeded {}/{} operations", existing + inserted, properties.count)
        }
        return inserted
    }

    /** An operation dated within the past year, for one of [SeedProperties.clients] clients. */
    private fun randomOperation(now: LocalDateTime) = BankingOperation(
        clientName = "Client ${random.nextInt(properties.clients)}",
        amount = random.nextLong(1, 1_000_000),
        operationDate = now.minusMinutes(random.nextLong(0, MINUTES_PER_YEAR)),
        operationType = if (random.nextBoolean()) OperationType.CREDIT else OperationType.DEBIT,
    )

    private companion object {
        const val MINUTES_PER_YEAR = 365L * 24 * 60
    }
}
