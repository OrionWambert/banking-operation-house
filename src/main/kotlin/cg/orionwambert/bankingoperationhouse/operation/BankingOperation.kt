package cg.orionwambert.bankingoperationhouse.operation

import jakarta.persistence.*
import java.time.LocalDateTime

/**
 * A debit or credit on a client account.
 *
 * Column names are part of the CDC contract: PeerDB replicates this table as-is to
 * ClickHouse (`banking.public_banking_operation`), where the dashboards query them.
 */
@Entity
@Table(name = "banking_operation")
class BankingOperation(
    @field:Id
    @field:GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "banking_operation_seq")
    @field:SequenceGenerator(name = "banking_operation_seq", sequenceName = "banking_operation_seq", allocationSize = 50)
    var id: Long? = null,

    @field:Column(name = "client_name", nullable = false)
    var clientName: String = "",

    /** Amount in the smallest currency unit, always positive; the direction is [operationType]. */
    @field:Column(name = "amount", nullable = false)
    var amount: Long = 0,

    @field:Column(name = "operation_date", nullable = false)
    var operationDate: LocalDateTime = LocalDateTime.now(),

    @field:Enumerated(EnumType.STRING)
    @field:Column(name = "operation_type", nullable = false, length = 16)
    var operationType: OperationType = OperationType.CREDIT,
)

enum class OperationType {
    DEBIT,
    CREDIT,
}
