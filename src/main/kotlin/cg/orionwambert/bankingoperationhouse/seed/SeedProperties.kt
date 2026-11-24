package cg.orionwambert.bankingoperationhouse.seed

import org.springframework.boot.context.properties.ConfigurationProperties

/** Demo data generation, configured under `app.seed`. */
@ConfigurationProperties("app.seed")
data class SeedProperties(
    /** Generate demo operations at startup. */
    val enabled: Boolean = false,
    /** Number of operations the table should hold once seeding is done. */
    val count: Int = 1_000_000,
    /** Operations saved per transaction. */
    val chunkSize: Int = 1_000,
    /** Number of distinct synthetic clients the operations are spread over. */
    val clients: Int = 1_000,
) {
    init {
        require(count >= 0) { "app.seed.count must be >= 0" }
        require(chunkSize > 0) { "app.seed.chunk-size must be > 0" }
        require(clients > 0) { "app.seed.clients must be > 0" }
    }
}
