package cg.orionwambert.bankingoperationhouse.operation

import org.springframework.data.jpa.repository.JpaRepository

interface BankingOperationRepository : JpaRepository<BankingOperation, Long>
