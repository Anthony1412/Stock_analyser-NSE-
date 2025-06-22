from flask import render_template, request, redirect, session

def handle_login(db):
    if request.method == 'GET':
        return render_template('login.html')
    email = request.form['email']
    password = request.form['password']
    user = db.users.find_one({'email': email})

    if user and user['password'] == password:
        session['user'] = email
        return redirect('/')
    elif not user:
        db.users.insert_one({'email': email, 'password': password, 'watchlist': []})
        session['user'] = email
        return redirect('/')
    return render_template('login.html', error="Invalid login")
