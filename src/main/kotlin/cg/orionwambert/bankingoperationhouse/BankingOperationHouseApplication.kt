package cg.orionwambert.bankingoperationhouse

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.context.properties.ConfigurationPropertiesScan
import org.springframework.boot.runApplication

@SpringBootApplication
@ConfigurationPropertiesScan
class BankingOperationHouseApplication

fun main(args: Array<String>) {
    runApplication<BankingOperationHouseApplication>(*args)
}
