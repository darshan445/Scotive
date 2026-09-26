# frozen_string_literal: true

namespace :simulate do
  desc "Seed QBO + Unipile conversations, then run onboarding / sync / webhook paths (script/simulate)"
  task ar: :environment do
    $stdout.sync = true
    require Rails.root.join("script/simulate/runner")
    args = ARGV.drop_while { |arg| arg != "--" }.drop(1)
    Simulate::Runner.from_argv(args).run!
    exit 0
  end
end
