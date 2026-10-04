pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "FluxPay"

include(":app")

include(":core:common")
include(":core:ui")
include(":core:domain")
include(":core:data")
include(":core:network")
include(":core:database")

include(":feature:auth")
include(":feature:dashboard")
include(":feature:transfer")
include(":feature:transactions")
include(":feature:settings")
include(":feature:budget")
