package cg.orionwambert.bankingoperationhouse

import org.springframework.boot.test.context.TestConfiguration
import org.springframework.boot.testcontainers.service.connection.ServiceConnection
import org.springframework.context.annotation.Bean
import org.testcontainers.postgresql.PostgreSQLContainer

/** Same Postgres major version as compose.yaml, shared by every test context. */
@TestConfiguration(proxyBeanMethods = false)
class TestcontainersConfiguration {

    @Bean
    @ServiceConnection
    fun postgres() = PostgreSQLContainer("postgres:18")
}
