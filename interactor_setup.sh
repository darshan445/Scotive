#!/usr/bin/env bash
# =============================================================================
# interactor_setup.sh
#
# Installs the Mother Goose interactor pattern into any Rails project.
# Run from the Rails root directory:
#
#   bash interactor_setup.sh
#
# What it creates:
#   app/interactors/concerns/log_helper.rb
#   app/interactors/concerns/execute_method_helper.rb
#   app/interactors/my_class.rb                       (example interactor)
#   lib/generators/interactor/interactor_generator.rb
#   lib/generators/interactor/templates/interactor_template.rb.erb
#   lib/generators/interactor/templates/interactor_spec_template.rb.erb
#   lib/generators/interactor/interactor_generator_manual.md
#   spec/interactors/my_class_spec.rb                 (example spec)
# =============================================================================

set -e

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[created]${RESET}  $1"; }
skip() { echo -e "${YELLOW}[exists] ${RESET}  $1 — skipped (already present)"; }
info() { echo -e "${CYAN}$1${RESET}"; }

# ── guard: must be a Rails root ────────────────────────────────────────────────
if [ ! -f "Gemfile" ] || [ ! -d "app" ]; then
  echo "ERROR: Run this script from the root of a Rails project (Gemfile + app/ must exist)."
  exit 1
fi

info "\n=== Installing Mother Goose interactor pattern ===\n"

# ── helper: write file only if it does not already exist ──────────────────────
write_file() {
  local path="$1"
  local content="$2"
  if [ -f "$path" ]; then
    skip "$path"
    return
  fi
  mkdir -p "$(dirname "$path")"
  printf '%s' "$content" > "$path"
  ok "$path"
}

# =============================================================================
# 1.  app/interactors/concerns/log_helper.rb
# =============================================================================
write_file "app/interactors/concerns/log_helper.rb" \
'# frozen_string_literal: true

module LogHelper
  def log_error(error)
    call_stack = caller
    class_filename = self.class.to_s.underscore + ".rb"
    caller_info = call_stack.find { |line| line.include?(class_filename) }
    file_line_info = caller_info.match(/(.*):(\d+):in/)
    Rails.logger.error "███ ERROR! ███ file #{self.class} at [#{file_line_info[1]} line #{file_line_info[2]} ]: #{error} ███"
  end

  # Raises if the child interactor failed, so the parent execute block catches it.
  def validate_result(open_struct_result)
    return open_struct_result if open_struct_result.success?

    log_error(open_struct_result.errors.to_s)
    raise StandardError, open_struct_result.errors
  end

  # Like validate_result but does NOT raise — just logs and returns the struct.
  def validate_result_without_raising_error(open_struct_result)
    log_error(open_struct_result.errors.to_s) if open_struct_result.errors.present?

    open_struct_result
  end

  def raise_string_error(error_message_string)
    log_error(error_message_string)
    raise StandardError, error_message_string
  end

  # Convenience for controllers: returns .data on success, .errors on failure.
  def handle_open_struct_response(open_struct)
    open_struct.success? ? open_struct.data : open_struct.errors
  end
end
'

# =============================================================================
# 2.  app/interactors/concerns/execute_method_helper.rb
# =============================================================================
write_file "app/interactors/concerns/execute_method_helper.rb" \
'# frozen_string_literal: true

require_relative "log_helper"

module ExecuteMethodHelper
  include LogHelper

  # Wraps the execute block: success returns OpenStruct(success?: true, data: <last value>).
  # Any StandardError is caught and returns OpenStruct(success?: false, errors: <message>).
  def execute_log_and_return_open_struct(&block)
    data = block.call
    OpenStruct.new(success?: true, data: data)
  rescue StandardError => e
    log_error(e)
    OpenStruct.new(success?: false, errors: e.message)
  end
end
'

# =============================================================================
# 3.  app/interactors/my_class.rb  — canonical example interactor
# =============================================================================
write_file "app/interactors/my_class.rb" \
'# frozen_string_literal: true

# MyClass Interactor
# Purpose: Example interactor — replace with your own logic.
# Methods:
# - execute

class MyClass
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(argument)
    new(argument).execute
  end

  def initialize(argument)
    @argument = argument
  end

  def execute
    execute_log_and_return_open_struct do
      # Business logic goes here.
      # The LAST expression becomes result.data on success.
      # Call raise_string_error("msg") or validate_result(OtherClass.execute(...))
      # to surface failures — they are caught and become result.errors.
      argument
    end
  end

  private

  attr_reader :argument
end
'

# =============================================================================
# 4.  lib/generators/interactor/interactor_generator.rb
# =============================================================================
write_file "lib/generators/interactor/interactor_generator.rb" \
'# frozen_string_literal: true

module Interactor
  class InteractorGenerator < Rails::Generators::Base
    source_root File.expand_path("templates", __dir__)

    argument :class_name, type: :string, default: "MyClass"

    def create_interactor_file
      template "interactor_template.rb.erb",
               File.join("app/interactors", "#{file_name}.rb")
    end

    def create_rspec_file
      template "interactor_spec_template.rb.erb",
               File.join("spec/interactors", "#{file_name}_spec.rb")
    end

    private

    def file_name
      class_name.underscore
    end

    def class_name_camelized
      class_name.camelize
    end
  end
end
'

# =============================================================================
# 5.  lib/generators/interactor/templates/interactor_template.rb.erb
# =============================================================================
write_file "lib/generators/interactor/templates/interactor_template.rb.erb" \
'# frozen_string_literal: true

# <%= class_name_camelized %> Interactor
# Purpose: [DESCRIBE WHAT THIS INTERACTOR DOES]
# Methods:
# - execute

class <%= class_name_camelized %>
  include ExecuteMethodHelper
  include LogHelper

  def self.execute(argument)
    new(argument).execute
  end

  def initialize(argument)
    @argument = argument
  end

  def execute
    execute_log_and_return_open_struct do
      # Your code here.
      # The last line of this block becomes result.data on success.
      # Use raise_string_error("msg") or validate_result(Other.execute(...)) for failures.
      argument
    end
  end

  private

  attr_reader :argument
end
'

# =============================================================================
# 6.  lib/generators/interactor/templates/interactor_spec_template.rb.erb
# =============================================================================
write_file "lib/generators/interactor/templates/interactor_spec_template.rb.erb" \
'# frozen_string_literal: true

require "rails_helper"

RSpec.describe <%= class_name_camelized %>, type: :interactor do
  describe ".execute" do
    let(:argument) { "argument_value" }

    subject { described_class.execute(argument) }

    context "when everything is valid" do
      it "returns success with data" do
        expect(subject.success?).to be true
        expect(subject.data).not_to be_nil
      end
    end

    context "when the argument is invalid" do
      let(:argument) { nil }

      it "returns failure with errors" do
        expect(subject.success?).to be false
        expect(subject.errors).to be_present
      end
    end
  end
end
'

# =============================================================================
# 7.  spec/interactors/my_class_spec.rb  — example spec
# =============================================================================
write_file "spec/interactors/my_class_spec.rb" \
'# frozen_string_literal: true

require "rails_helper"

RSpec.describe MyClass, type: :interactor do
  describe ".execute" do
    let(:argument) { "hello" }

    subject { described_class.execute(argument) }

    context "when everything is valid" do
      it "returns success with data" do
        expect(subject.success?).to be true
        expect(subject.data).to eq("hello")
      end
    end

    context "when the argument is invalid" do
      let(:argument) { nil }

      it "returns failure with errors" do
        # Adjust this expectation once you add real validation in MyClass.
        expect(subject.success?).to be true
      end
    end
  end
end
'

# =============================================================================
# 8.  lib/generators/interactor/interactor_generator_manual.md
# =============================================================================
write_file "lib/generators/interactor/interactor_generator_manual.md" \
'# Interactor Pattern — Developer Manual

## Overview

Interactors are plain Ruby command objects that encapsulate a single use case or
pipeline step.  Each one exposes a class-level `.execute` method and returns an
`OpenStruct` so callers always have a consistent shape to work with:

```ruby
result = MyInteractor.execute(some_arg)
result.success?  # => true / false
result.data      # present when success? is true  (last value in the block)
result.errors    # present when success? is false (the exception message)
```

---

## Generate a new interactor

```bash
# Simple (top-level class)
bin/rails generate interactor MyClassName

# Namespaced (creates module folder automatically)
bin/rails generate interactor Payments::ChargeCard
```

Each invocation creates:

| File | Purpose |
|------|---------|
| `app/interactors/<name>.rb` | The interactor class |
| `spec/interactors/<name>_spec.rb` | Skeleton RSpec file |

---

## Anatomy of an interactor

```ruby
# frozen_string_literal: true

class DoSomething
  include ExecuteMethodHelper   # provides execute_log_and_return_open_struct
  include LogHelper             # provides raise_string_error, validate_result, ...

  # 1. Class-level entry point — always call this from outside.
  def self.execute(user_id:, order_id:)
    new(user_id: user_id, order_id: order_id).execute
  end

  # 2. Store dependencies in ivars.
  def initialize(user_id:, order_id:)
    @user_id  = user_id
    @order_id = order_id
  end

  # 3. execute wraps work in the helper block.
  def execute
    execute_log_and_return_open_struct do
      user  = find_user!
      order = find_order!
      process(user, order)   # last value becomes result.data
    end
  end

  private

  attr_reader :user_id, :order_id

  def find_user!
    User.find(user_id)
  rescue ActiveRecord::RecordNotFound
    raise_string_error("User #{user_id} not found")
  end

  def find_order!
    Order.find(order_id)
  rescue ActiveRecord::RecordNotFound
    raise_string_error("Order #{order_id} not found")
  end

  def process(user, order)
    # ... your business logic ...
    order
  end
end
```

---

## Key helpers (LogHelper)

| Method | When to use |
|--------|-------------|
| `raise_string_error("msg")` | Raise a user-friendly error anywhere; logs it and raises StandardError. |
| `validate_result(Other.execute(...))` | Call a child interactor and re-raise its error if it failed. |
| `validate_result_without_raising_error(result)` | Same, but does not raise (use for non-fatal flows). |
| `handle_open_struct_response(result)` | Controller convenience: returns .data on success, .errors on failure. |

---

## Composing interactors

```ruby
def execute
  execute_log_and_return_open_struct do
    token  = validate_result(Auth::GetToken.execute(user_id: user_id)).data
    result = validate_result(Api::PostPayload.execute(token: token, payload: payload)).data
    result
  end
end
```

If either child interactor fails, validate_result raises, the wrapper catches it,
and the parent returns { success?: false, errors: "child error message" } automatically.

---

## Controller usage

```ruby
def create
  result = DoSomething.execute(user_id: current_user.id, order_id: params[:order_id])

  if result.success?
    render json: result.data, status: :created
  else
    render json: { error: result.errors }, status: :unprocessable_entity
  end
end
```

---

## File layout

```
app/
  interactors/
    concerns/
      log_helper.rb             <- LogHelper module
      execute_method_helper.rb  <- ExecuteMethodHelper module
    my_feature/
      do_something.rb           <- interactors grouped by domain
      do_something_else.rb
spec/
  interactors/
    my_feature/
      do_something_spec.rb
lib/
  generators/
    interactor/
      interactor_generator.rb
      interactor_generator_manual.md   <- this file
      templates/
        interactor_template.rb.erb
        interactor_spec_template.rb.erb
```

---

*Pattern originally developed for Mother Goose (mg-backend).*
'

# =============================================================================
# Done
# =============================================================================
echo ""
info "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Autoload the concerns (Rails 6 Zeitwerk should pick them up automatically"
echo "     if app/interactors/concerns/ is under an autoloaded path)."
echo "     If not, add this to config/application.rb:"
echo '       config.autoload_paths += [Rails.root.join("app/interactors")]'
echo ""
echo "  2. Generate your first real interactor:"
echo '       bin/rails generate interactor MyFeature::DoSomething'
echo ""
echo "  3. Delete the example files once you no longer need them:"
echo "       app/interactors/my_class.rb"
echo "       spec/interactors/my_class_spec.rb"
echo ""
