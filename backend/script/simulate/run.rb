# frozen_string_literal: true

# bin/rails runner script/simulate/run.rb -- --mode=onboarding
require_relative "runner"

Simulate::Runner.from_argv(ARGV).run!
